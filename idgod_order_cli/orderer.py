from __future__ import annotations

import json
import re
import tempfile
import time
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from .btcpay import PaymentDetails, fetch_btcpay_from_page
from .cache import OrderCache, default_cache_dir
from .captcha import (
    CAPTCHA_LEN_MAX,
    CAPTCHA_LEN_MIN,
    CaptchaSolverError,
    best_captcha_guess,
    normalize_captcha_text,
    solve_captcha_image,
)
from .models import CheckoutFillMeta, CheckoutResult, OrderResult, Person, ShippingInfo
from .proxies import ProxyConfig, TorManager, pick_working_proxy
from .selectors import (
    CART_BUTTONS,
    CART_SELECTORS,
    DEFAULT_SHIPPING_VALUE,
    PAYMENT_LABELS,
    SELECTORS,
    SHIPPING_ALIASES,
)
from .states import (
    StateOption,
    estimate_price,
    expand_state_name,
    map_eye_color,
    map_hair_color,
    map_sex,
    parse_height,
    pick_state_option,
    variant_from_product_id,
)

ORDER_URL = "https://www.idgod.ph/order"
CART_URL = "https://www.idgod.ph/cart"
DEFAULT_DISCOUNT = ""
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


async def fetch_vendor_image_bytes(url: str, *, timeout: float = 30.0) -> bytes:
    """Download export/vendor image URLs over a direct connection (not Tor/proxy)."""
    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=timeout,
        headers={"User-Agent": USER_AGENT, "Accept": "image/*,*/*"},
    ) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.content


async def _resolve_image(
    source: str,
    fallback: str = "",
) -> Path:
    src = source.strip()
    if src.startswith(("http://", "https://")):
        try:
            content = await fetch_vendor_image_bytes(src)
            suffix = Path(urlparse(src).path).suffix or ".jpg"
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
            tmp.write(content)
            tmp.close()
            return _prepare_upload_image(Path(tmp.name))
        except Exception:
            if fallback:
                src = fallback
            else:
                raise ValueError(
                    f"Image URL failed and no fallback set: {source[:80]}..."
                ) from None

    if not src:
        raise ValueError("No photo/signature provided and no fallback set")

    p = Path(src).expanduser()
    if not p.exists():
        raise FileNotFoundError(f"Image not found: {src}")
    return _prepare_upload_image(p)


def _parse_money(text: str) -> float | None:
    m = re.search(r"\$?\s*([\d,]+\.?\d*)", text.replace(",", ""))
    return float(m.group(1)) if m else None


def _prepare_upload_image(path: Path) -> Path:
    """Normalize vendor WebP / huge uploads for idgod's file inputs."""
    try:
        size = path.stat().st_size
        suffix = path.suffix.lower()
        if suffix not in {".webp", ".png"} and size <= 4_000_000:
            return path
        from PIL import Image

        img = Image.open(path)
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        if max(img.size) > 1800:
            img.thumbnail((1800, 1800))
        out = Path(tempfile.mktemp(suffix=".jpg"))
        img.save(out, "JPEG", quality=88, optimize=True)
        return out
    except Exception:
        return path


def _extract_order_error(body: str) -> str:
    for line in body.splitlines():
        text = line.strip()
        if not text:
            continue
        if re.search(
            r"couldn't add|highlighted fields|required|invalid|error|new photo is required",
            text,
            re.I,
        ):
            return text
    return "Order form rejected — check required fields and photo upload"


async def _wait_for_submit_result(page, *, checkout: bool, timeout_ms: int) -> tuple[bool, str]:
    """Wait for add-to-cart or checkout redirect; surface validation errors."""
    email_sel = CART_SELECTORS["email"]
    deadline = time.time() + timeout_ms / 1000
    stable_ok = 0
    while time.time() < deadline:
        body = await page.inner_text("body")
        if re.search(
            r"couldn't add that card|please check the highlighted fields|new photo is required",
            body,
            re.I,
        ):
            return False, _extract_order_error(body)

        if checkout:
            if await page.locator(email_sel).count():
                return True, ""
            if CART_URL in page.url and await page.locator(CART_SELECTORS["name"]).count():
                return True, ""
        else:
            stable_ok += 1
            if stable_ok >= 3:
                return True, ""

        await page.wait_for_timeout(1000)

    if checkout and await page.locator(email_sel).count():
        return True, ""
    if checkout:
        return False, f"Timed out waiting for cart checkout (last URL: {page.url})"
    return False, "Timed out waiting for add-to-cart confirmation"


async def _ensure_cart_checkout_page(page, *, timeout_ms: int) -> tuple[bool, str]:
    if await page.locator(CART_SELECTORS["email"]).count():
        return True, ""
    if CART_URL not in page.url:
        try:
            await page.goto(CART_URL, wait_until="domcontentloaded", timeout=timeout_ms)
        except Exception as e:
            return False, f"Failed to open cart: {e}"
    deadline = time.time() + timeout_ms / 1000
    while time.time() < deadline:
        if await page.locator(CART_SELECTORS["email"]).count():
            return True, ""
        await page.wait_for_timeout(1000)
    body = await page.inner_text("body")
    if re.search(r"cart contents\s*\(0\)|your cart is empty|start order now", body, re.I):
        return False, "Cart is empty — order form submit did not add an ID"
    return False, "Cart checkout form not found (#id_email missing)"


class IdGodOrderer:
    def __init__(
        self,
        *,
        headless: bool = True,
        discount_code: str = DEFAULT_DISCOUNT,
        fallback_photo: str = "",
        fallback_signature: str = "",
        cheapest_state: bool = True,
        state_variants: dict[str, str] | None = None,
        dry_run: bool = False,
        timeout_ms: int = 60000,
        proxies: list[ProxyConfig] | None = None,
        use_tor: bool = False,
        auto_proxy: bool = False,
        checkout: bool = False,
        checkout_submit: bool = False,
        captcha_solver: str = "auto",
        twocaptcha_key: str = "",
        captcha_attempts: int = 15,
        shipping: ShippingInfo | None = None,
        payment_method: str = "",
        shipping_method: str = "",
        debug_dir: str = "",
        input_file: str = "",
        cache_dir: str = "",
        use_cache: bool = True,
        fetch_payment: bool = False,
        transport: str = "http",
        require_coupon: bool = True,
        ui: Any = None,
    ):
        self.headless = headless
        self.discount_code = discount_code
        self.fallback_photo = fallback_photo
        self.fallback_signature = fallback_signature
        self.cheapest_state = cheapest_state
        self.state_variants = state_variants or {}
        self.dry_run = dry_run
        self.timeout_ms = timeout_ms
        self.proxies = proxies or []
        self.use_tor = use_tor
        self.auto_proxy = auto_proxy
        self.checkout = checkout
        self.checkout_submit = checkout_submit
        self.captcha_solver = captcha_solver
        self.twocaptcha_key = twocaptcha_key
        self.captcha_attempts = max(1, captcha_attempts)
        self.shipping = shipping or ShippingInfo()
        self.payment_method = payment_method
        self.shipping_method = shipping_method
        self.debug_dir = Path(debug_dir).expanduser() if debug_dir else None
        self.input_file = input_file
        self.cache_dir = cache_dir
        self.use_cache = use_cache
        self.fetch_payment = fetch_payment
        self.transport = transport
        self.require_coupon = require_coupon
        self.ui = ui
        self._tor_mgr = TorManager()
        self._active_proxy: ProxyConfig | None = None
        self._probe_results: list[dict] = []
        self._http_finish_response = None

    async def _resolve_proxy(self) -> ProxyConfig | None:
        if self.use_tor:
            if self.ui:
                self.ui.phase("Routing")
                self.ui.step("Starting Tor…")
            self._active_proxy = self._tor_mgr.start()
            if self.ui:
                self.ui.ok(f"Tor ready ({self._active_proxy.display})")
            return self._active_proxy

        if not self.proxies:
            return None

        if not self.auto_proxy:
            self._active_proxy = self.proxies[0]
            if self.ui:
                self.ui.phase("Routing")
                self.ui.ok(f"Using proxy {self._active_proxy.display}")
            return self._active_proxy

        if self.ui:
            self.ui.phase("Routing")
            self.ui.step(f"Probing {len(self.proxies)} proxy(s)…")
        working, results = await pick_working_proxy(self.proxies, ORDER_URL)
        self._probe_results = results
        self._active_proxy = working
        if self.ui:
            if working:
                self.ui.ok(f"Proxy OK: {working.display}")
            else:
                self.ui.fail("No working proxy found")
        return working

    def _launch_kwargs(self, proxy: ProxyConfig | None) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "headless": self.headless,
            "args": ["--no-sandbox", "--disable-dev-shm-usage"],
        }
        if proxy:
            kwargs["proxy"] = proxy.to_playwright()
        return kwargs

    async def _launch_browser(self, pw):
        kwargs = self._launch_kwargs(self._active_proxy)
        try:
            return await pw.chromium.launch(**kwargs)
        except Exception:
            return await pw.chromium.launch(channel="chrome", **kwargs)

    async def _fill_by_label(self, page, pattern: str, value: str) -> None:
        loc = page.get_by_label(re.compile(pattern, re.I))
        if await loc.count():
            await loc.first.fill(value)
            return
        raise RuntimeError(f"Field not found: {pattern}")

    async def _fill_sel(self, page, key: str, value: str) -> None:
        sel = SELECTORS[key]
        loc = page.locator(sel)
        if await loc.count() == 0:
            raise RuntimeError(f"Field not found: {key} ({sel})")
        await loc.fill(value)

    async def _select_sel(self, page, key: str, *, label: str | None = None, value: str | None = None) -> None:
        loc = page.locator(SELECTORS[key])
        if await loc.count() == 0:
            raise RuntimeError(f"Select not found: {key}")
        if label:
            await loc.select_option(label=label)
        elif value:
            await loc.select_option(value=value)

    async def _get_state_options(self, page) -> list[StateOption]:
        select = page.locator("select").filter(has=page.locator("option")).first
        options: list[StateOption] = []
        opts = await select.locator("option").all()
        for opt in opts:
            label = (await opt.inner_text()).strip()
            value = await opt.get_attribute("value")
            if not label or not value or label.lower() in ("select", "choose", ""):
                continue
            options.append(StateOption(label=label, price=estimate_price(label)))
        return options

    async def _fill_person(self, page, person: Person, *, checkout: bool = False) -> OrderResult:
        if self.ui:
            self.ui.detail(f"Selecting state for {person.state}")
        state_options = await self._get_state_options(page)
        state_name = expand_state_name(person.state)
        variant = (
            person.state_variant
            or self.state_variants.get(state_name, "")
            or self.state_variants.get(person.state, "")
            or variant_from_product_id(person.product_id)
        )
        chosen, note = pick_state_option(
            state_name,
            state_options,
            variant=variant,
            cheapest=self.cheapest_state,
        )
        if chosen is None:
            return OrderResult(person=person, success=False, message=note)

        feet, inches = parse_height(person.height or "5'6\"")
        try:
            if self.ui:
                self.ui.detail(f"Filling form: {person.display_name}")
            await self._fill_sel(page, "first_name", person.first_name)
            if person.middle_name:
                await self._fill_sel(page, "middle_name", person.middle_name)
            await self._fill_sel(page, "last_name", person.last_name)
            await self._fill_sel(page, "date_of_birth", person.dob)

            await self._select_sel(page, "state", label=chosen.label)

            await self._fill_sel(page, "height_feet", feet)
            await self._fill_sel(page, "height_inches", inches)
            await self._fill_sel(page, "weight", person.weight or "130")

            await self._select_sel(page, "eyes", label=map_eye_color(person.eye_color or "Brown"))
            await self._select_sel(page, "hair", label=map_hair_color(person.hair_color or "Brown"))
            await self._select_sel(page, "gender", label=map_sex(person.sex or "Female"))

            if person.street:
                await self._fill_sel(page, "address1", person.street)
            await self._fill_sel(page, "city", person.city)
            await self._fill_sel(page, "zip", person.zip)

            # Trigger validation hooks on inputs
            for key in ("date_of_birth", "height_feet", "height_inches", "weight", "city", "zip"):
                await page.locator(SELECTORS[key]).dispatch_event("change")
                await page.locator(SELECTORS[key]).dispatch_event("blur")

            photo_path = await _resolve_image(person.photo, self.fallback_photo)
            if self.ui:
                self.ui.detail("Uploading photo")
            await page.locator(SELECTORS["picture"]).set_input_files(str(photo_path))
            await page.wait_for_timeout(1500)

            if person.signature or self.fallback_signature:
                if self.ui:
                    self.ui.detail("Uploading signature")
                sig_path = await _resolve_image(person.signature, self.fallback_signature)
                sig_loc = page.locator(SELECTORS["signature"])
                if await sig_loc.count():
                    await sig_loc.set_input_files(str(sig_path))
                    await page.wait_for_timeout(1000)

            if person.issue_date:
                extra = page.locator(SELECTORS["custom_license_number"])
                if await extra.count():
                    await extra.fill(person.issue_date)

            msg = note or f"Filled form for {person.display_name}"
            if self.dry_run:
                return OrderResult(
                    person=person,
                    success=True,
                    message=f"[dry-run] {msg}",
                    state_selected=chosen.label,
                    price=chosen.price,
                )

            action_val = "2" if checkout else "1"
            submit = page.locator(f'button[name="action"][value="{action_val}"]')
            if self.ui:
                dest = "checkout" if checkout else "cart"
                self.ui.step(f"Submitting → {dest}")

            try:
                async with page.expect_navigation(timeout=min(self.timeout_ms, 45000)):
                    await page.evaluate(
                        """(actionVal) => {
                          const form = document.getElementById('order-form');
                          if (!form) throw new Error('order-form missing');
                          if (window.jQuery) {
                            const $f = window.jQuery(form);
                            if ($f.data('bs.validator')) $f.validator('destroy');
                          }
                          const btn = form.querySelector(`button[name="action"][value="${actionVal}"]`);
                          if (!btn) throw new Error('submit button missing');
                          form.requestSubmit(btn);
                        }""",
                        action_val,
                    )
            except Exception:
                await submit.first.click()

            ok_submit, submit_msg = await _wait_for_submit_result(
                page,
                checkout=checkout,
                timeout_ms=max(self.timeout_ms, 120000 if checkout else 60000),
            )
            if not ok_submit:
                return OrderResult(
                    person=person,
                    success=False,
                    message=submit_msg,
                    state_selected=chosen.label,
                )

            await page.wait_for_load_state("domcontentloaded")
            await page.wait_for_timeout(500)

            if self.ui:
                self.ui.ok(f"{person.display_name} · {chosen.label}")

            return OrderResult(
                person=person,
                success=True,
                message=msg,
                state_selected=chosen.label,
                price=chosen.price,
            )
        except Exception as e:
            return OrderResult(
                person=person,
                success=False,
                message=str(e),
                state_selected=chosen.label,
            )

    async def _apply_discount(self, page) -> tuple[bool, str]:
        if not self.discount_code:
            return False, "No discount code"

        coupon = page.locator(CART_SELECTORS["coupon"])
        if await coupon.count():
            await coupon.fill(self.discount_code)
            update = page.locator(CART_BUTTONS["update"])
            if await update.count():
                try:
                    async with page.expect_navigation(timeout=self.timeout_ms):
                        await update.click()
                except Exception:
                    await update.click()
                    await page.wait_for_timeout(2500)
            await page.wait_for_load_state("domcontentloaded")
            body = await page.content()
            if re.search(r"invalid|not found|expired|does not exist", body, re.I):
                return False, f"Discount code '{self.discount_code}' rejected on cart page"
            return True, f"Applied coupon '{self.discount_code}' on cart (clicked UPDATE)"

        # Fallback heuristics for other pages
        for pattern in [
            page.get_by_placeholder(re.compile(r"coupon|discount|promo", re.I)),
            page.locator("input[name*='coupon' i], input[name*='discount' i]"),
        ]:
            if await pattern.count():
                await pattern.first.fill(self.discount_code)
                apply_btn = page.get_by_role("button", name=re.compile(r"apply|redeem|update", re.I))
                if await apply_btn.count():
                    await apply_btn.first.click()
                    await page.wait_for_timeout(2000)
                    return True, f"Applied code {self.discount_code}"
                break
        return False, (
            f"No coupon field found — email idgod@idgod.ph to apply '{self.discount_code}'"
        )

    def _resolve_payment_label(self) -> str:
        if not self.payment_method:
            return ""
        key = self.payment_method.strip().lower()
        return PAYMENT_LABELS.get(key, self.payment_method)

    def _resolve_shipping_label(self) -> str:
        if not self.shipping_method:
            return ""
        key = self.shipping_method.strip().lower()
        for alias, label in SHIPPING_ALIASES.items():
            if alias in key:
                return label
        return self.shipping_method

    async def _fill_cart_field(self, page, key: str, value: str, filled: list[str], missing: list[str]) -> None:
        if not value:
            missing.append(key)
            return
        loc = page.locator(CART_SELECTORS[key])
        if await loc.count() == 0:
            missing.append(key)
            return
        await loc.fill(value)
        filled.append(key)

    async def _fetch_captcha_image(self, page) -> bytes:
        img = page.locator(CART_SELECTORS["captcha_image"]).first
        if await img.count() == 0:
            raise CaptchaSolverError("Captcha image not found on cart page")

        await img.wait_for(state="visible", timeout=self.timeout_ms)
        await page.wait_for_timeout(400)

        # In-page fetch uses the same Tor/proxy session + cookies as the visible image.
        try:
            data = await page.evaluate(
                """async () => {
                  const img = document.querySelector('img.captcha, img[src*="/captcha/image/"]');
                  if (!img || !img.src) return null;
                  if (!img.complete) {
                    await new Promise((resolve, reject) => {
                      img.onload = resolve;
                      img.onerror = reject;
                      setTimeout(resolve, 1500);
                    });
                  }
                  const r = await fetch(img.src, {credentials: 'same-origin'});
                  if (!r.ok) return null;
                  const buf = await r.arrayBuffer();
                  return Array.from(new Uint8Array(buf));
                }"""
            )
            if data:
                body = bytes(data)
                if body[:8] == b"\x89PNG\r\n\x1a\n":
                    return body
        except Exception:
            pass

        src = await img.get_attribute("src")
        if src:
            full_url = urljoin(page.url, src)
            try:
                resp = await page.request.get(full_url)
                if resp.ok:
                    body = await resp.body()
                    if body and body[:8] == b"\x89PNG\r\n\x1a\n":
                        return body
            except Exception:
                pass

        shot = await img.screenshot()
        if shot and shot[:8] == b"\x89PNG\r\n\x1a\n":
            return shot
        raise CaptchaSolverError("Captcha image bytes are not a valid PNG")

    async def _save_captcha_debug(self, image_bytes: bytes, label: str) -> Path:
        base = self.debug_dir
        if not base:
            base = default_cache_dir() / "captcha-debug"
        base.mkdir(parents=True, exist_ok=True)
        safe = re.sub(r"[^a-z0-9_-]+", "-", label.lower()).strip("-")
        stamp = time.strftime("%Y%m%d-%H%M%S")
        path = base / f"captcha-{stamp}-{safe}.png"
        path.write_bytes(image_bytes)
        return path

    async def _refresh_captcha(self, page) -> None:
        img = page.locator(CART_SELECTORS["captcha_image"]).first
        if await img.count():
            try:
                await img.click()
                await page.wait_for_timeout(900)
                return
            except Exception:
                pass

        refresh = page.locator(
            'a[href*="captcha/refresh"], .captcha-refresh, [onclick*="captcha"]'
        )
        if await refresh.count():
            await refresh.first.click()
            await page.wait_for_timeout(800)
            return

        try:
            await page.evaluate(
                """async () => {
                  const endpoints = ['/captcha/refresh/', '/captcha/refresh'];
                  for (const path of endpoints) {
                    try {
                      const r = await fetch(path, {credentials: 'same-origin'});
                      if (!r.ok) continue;
                      const data = await r.json();
                      const hash = document.querySelector('#id_captcha_0');
                      const image = document.querySelector('img.captcha, img[src*="/captcha/image/"]');
                      if (hash && data.key) hash.value = data.key;
                      if (image && data.image_url) image.src = data.image_url;
                      return;
                    } catch (e) {}
                  }
                }"""
            )
            await page.wait_for_timeout(500)
        except Exception:
            pass

    async def _submit_captcha_answer(self, page, captcha_input, text: str) -> bool:
        await captcha_input.fill(text)
        finish = page.locator(CART_BUTTONS["finish"])
        if not await finish.count():
            return False

        try:
            async with page.expect_navigation(timeout=self.timeout_ms):
                await finish.click()
        except Exception:
            await finish.click()
            await page.wait_for_timeout(2500)

        body = await page.content()
        if re.search(r"invalid captcha|incorrect captcha|captcha.*invalid", body, re.I):
            return False
        if await captcha_input.is_visible() and re.search(
            r"errorlist|alert-danger|has-error", body, re.I
        ):
            return False
        return True

    async def _solve_and_fill_captcha(
        self, page, *, max_attempts: int | None = None
    ) -> tuple[bool, str, str, int, int]:
        max_attempts = max_attempts or self.captcha_attempts
        started = time.time()
        attempts_used = 0
        captcha_input = page.locator(CART_SELECTORS["captcha"])
        if await captcha_input.count() == 0 or not await captcha_input.is_visible():
            return True, "No captcha on page", "", 0, 0

        if self.captcha_solver == "manual":
            return (
                False,
                "Captcha required — use --headed and solve manually, or set --captcha-solver ppllocr|2captcha",
                "",
                0,
                0,
            )

        last_error = ""
        solver_used = ""
        captcha_mode = self.captcha_solver
        if captcha_mode in ("ppllocr", "ddddocr"):
            captcha_mode = "auto"

        for attempt in range(1, max_attempts + 1):
            attempts_used = attempt

            try:
                await captcha_input.fill("")
            except Exception:
                pass

            if self.ui:
                self.ui.step(f"Attempt {attempt}/{max_attempts}: reading captcha image")

            try:
                image_bytes = await self._fetch_captcha_image(page)
                debug_path = await self._save_captcha_debug(image_bytes, f"attempt-{attempt}")
                votes = 1
                reads = 0
                result = await solve_captcha_image(
                    image_bytes,
                    mode=captcha_mode,
                    api_key=self.twocaptcha_key,
                )
                solver_used = result["solver"]
                raw_text = result.get("raw_text") or result["text"]
                guess = result.get("guess") or best_captcha_guess(raw_text)
                votes = result.get("consensus_votes", 1)
                reads = result.get("ocr_reads", 1)
            except CaptchaSolverError as e:
                last_error = str(e)
                continue

            if not guess:
                last_error = f"OCR returned empty captcha text (saved {debug_path})"
                if self.ui:
                    self.ui.warn(last_error)
                continue

            raw_len = len(normalize_captcha_text(raw_text))
            if raw_len < CAPTCHA_LEN_MIN or raw_len > CAPTCHA_LEN_MAX:
                last_error = (
                    f"OCR raw length {raw_len} for '{raw_text}', submitting trimmed guess '{guess}' "
                    f"(attempt {attempt}/{max_attempts}, image {debug_path})"
                )
                if self.ui:
                    self.ui.detail(f"OCR '{raw_text}' → trimmed '{guess}'")
            else:
                last_error = f"Trying '{guess}' from {solver_used} (attempt {attempt}/{max_attempts})"
                if self.ui:
                    self.ui.detail(
                        f"OCR guess '{guess}' ({solver_used}, {votes} vote(s), {reads} reads)"
                    )

            if await self._submit_captcha_answer(page, captcha_input, guess):
                solve_ms = int((time.time() - started) * 1000)
                if self.ui:
                    self.ui.ok(f"Captcha solved: {guess} ({solver_used}, {solve_ms}ms)")
                return (
                    True,
                    f"Captcha solved with {solver_used}: {guess}"
                    + (f" (raw OCR: {raw_text})" if guess != raw_text.lower() else ""),
                    solver_used,
                    solve_ms,
                    attempts_used,
                )
            last_error = f"Captcha rejected for '{guess}' (raw OCR: {raw_text}, attempt {attempt}/{max_attempts})"
            if self.ui:
                self.ui.warn(f"Rejected '{guess}' — refreshing")
            await self._refresh_captcha(page)

        solve_ms = int((time.time() - started) * 1000)
        if self.ui:
            self.ui.fail(last_error or "Captcha solving failed")
        return False, last_error or "Captcha solving failed", solver_used, solve_ms, attempts_used

    async def _fill_checkout(self, page) -> CheckoutFillMeta:
        shipping = self.shipping
        if shipping.is_local_delivery:
            required = {"email": shipping.email}
        else:
            required = {
                "email": shipping.email,
                "name": shipping.name,
                "address": shipping.street,
                "city": shipping.city,
                "state": shipping.state,
                "zip": shipping.zip,
            }
        missing_values = [key for key, value in required.items() if not value]
        if missing_values:
            msg = f"Missing checkout values: {', '.join(missing_values)}"
            if shipping.is_local_delivery:
                msg = (
                    f"{msg} (Local Delivery export — use --shipping or fill cart manually)"
                )
            return CheckoutFillMeta(
                completed=False,
                message=msg,
                filled=[],
                missing=missing_values,
            )

        filled: list[str] = []
        missing: list[str] = []
        captcha_solver = ""
        captcha_solved = False
        captcha_solve_time_ms = 0
        captcha_attempts_used = 0

        total_before, _ = await self._read_totals(page)

        if self.ui:
            self.ui.phase("Checkout")
            if shipping.is_local_delivery:
                self.ui.step("Local Delivery — filling email/payment only")
            else:
                self.ui.step("Filling shipping & payment")

        if not shipping.is_local_delivery:
            await self._fill_cart_field(page, "name", shipping.name, filled, missing)
        await self._fill_cart_field(page, "email", shipping.email, filled, missing)
        if shipping.phone.strip():
            await self._fill_cart_field(page, "phone", shipping.phone.strip(), filled, missing)
        if not shipping.is_local_delivery:
            await self._fill_cart_field(page, "address", shipping.street, filled, missing)
            await self._fill_cart_field(page, "city", shipping.city, filled, missing)
            await self._fill_cart_field(page, "state", shipping.state, filled, missing)
            await self._fill_cart_field(page, "zip", shipping.zip, filled, missing)
            await self._fill_cart_field(page, "country", shipping.country or "USA", filled, missing)

        pay_label = self._resolve_payment_label()
        if pay_label:
            pay_sel = page.locator(CART_SELECTORS["payment_method"])
            if await pay_sel.count():
                await pay_sel.select_option(label=pay_label)
                filled.append("payment_method")
            else:
                missing.append("payment_method")

        ship_label = self._resolve_shipping_label()
        pri_sel = page.locator(CART_SELECTORS["priority"])
        if await pri_sel.count():
            if ship_label:
                try:
                    await pri_sel.select_option(label=ship_label)
                except Exception:
                    await pri_sel.select_option(value=DEFAULT_SHIPPING_VALUE)
            else:
                await pri_sel.select_option(value=DEFAULT_SHIPPING_VALUE)
            filled.append("shipping_method")

        if self.discount_code:
            coupon = page.locator(CART_SELECTORS["coupon"])
            if await coupon.count():
                if self.ui:
                    self.ui.detail(f"Applying coupon {self.discount_code}")
                await coupon.fill(self.discount_code)
                filled.append("coupon")

        update = page.locator(CART_BUTTONS["update"])
        if await update.count() and filled:
            if self.ui:
                self.ui.step("Updating cart")
            await update.click()
            # Cart UPDATE is a same-page POST — no navigation event; don't wait 60s.
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=8000)
            except Exception:
                pass
            await page.wait_for_timeout(600)
            filled.append("cart_update")

        total_after, _ = await self._read_totals(page)

        if self.discount_code:
            from .http_forms import coupon_savings_message

            applied, msg, _ = coupon_savings_message(
                self.discount_code, total_before, total_after
            )
            if self.ui:
                if applied:
                    self.ui.ok(msg)
                elif msg:
                    self.ui.detail(msg)

        if self.checkout_submit:
            if self.ui:
                self.ui.phase("Captcha")
            ok, captcha_msg, captcha_solver, captcha_solve_time_ms, captcha_attempts_used = (
                await self._solve_and_fill_captcha(page)
            )
            if ok and captcha_solver:
                filled.append("captcha")
                captcha_solved = True
            elif not ok:
                missing.append("captcha")
                return CheckoutFillMeta(
                    completed=False,
                    message=captcha_msg,
                    filled=filled,
                    missing=missing,
                    captcha_solver=captcha_solver,
                    captcha_solved=captcha_solved,
                    captcha_solve_time_ms=captcha_solve_time_ms,
                    captcha_attempts_used=captcha_attempts_used,
                    total_before_discount=total_before,
                    total_after_discount=total_after,
                )
            else:
                finish = page.locator(CART_BUTTONS["finish"])
                if await finish.count():
                    try:
                        async with page.expect_navigation(timeout=self.timeout_ms):
                            await finish.click()
                    except Exception:
                        await finish.click()
                        await page.wait_for_timeout(3000)
                    filled.append("checkout_submit")
                else:
                    missing.append("checkout_submit")

        if self.checkout_submit and captcha_solved and "checkout_submit" not in filled:
            filled.append("checkout_submit")

        essential = {"email", "name", "address", "city", "state", "zip"}
        essential_missing = [m for m in missing if m in essential]
        completed = not essential_missing and (
            not self.checkout_submit or "checkout_submit" in filled
        )
        if "captcha" in missing:
            completed = False

        message = "Checkout fields filled on cart page"
        if self.checkout_submit and "checkout_submit" in filled:
            message = f"Order finished; URL: {page.url}"
            if captcha_solver:
                message += f" (captcha: {captcha_solver}, {captcha_solve_time_ms}ms)"
        elif missing:
            message = f"Checkout partially filled; missing: {', '.join(missing)}"

        if self.checkout_submit and completed:
            total_after, _ = await self._read_totals(page)

        return CheckoutFillMeta(
            completed=completed,
            message=message,
            filled=filled,
            missing=missing,
            captcha_solver=captcha_solver,
            captcha_solved=captcha_solved,
            captcha_solve_time_ms=captcha_solve_time_ms,
            captcha_attempts_used=captcha_attempts_used,
            total_before_discount=total_before,
            total_after_discount=total_after,
        )

    async def _read_totals(self, page) -> tuple[float | None, int]:
        total_el = page.locator("#total")
        total = None
        if await total_el.count():
            total = _parse_money(await total_el.first.inner_text())
        body = await page.content()
        if total is None:
            totals = re.findall(r"TOTAL:\s*\$?([\d,]+\.?\d*)", body, re.I)
            total = _parse_money(totals[-1]) if totals else None
        cart_match = re.search(r"cart contents\s*\((\d+)\)", body, re.I)
        count = int(cart_match.group(1)) if cart_match else 0
        if count == 0:
            items = await page.locator(".cart-item, [class*='cart'] tr, table tr").count()
            if items:
                count = max(items - 1, 0)
        return total, count

    async def _write_debug_dump(self, page, label: str) -> None:
        if not self.debug_dir:
            return
        self.debug_dir.mkdir(parents=True, exist_ok=True)
        safe = re.sub(r"[^a-z0-9_-]+", "-", label.lower()).strip("-")
        (self.debug_dir / f"{safe}.html").write_text(await page.content(), encoding="utf-8")
        controls = await page.evaluate(
            """() => [...document.querySelectorAll('input, select, textarea, button')].map((el) => ({
              tag: el.tagName.toLowerCase(),
              type: el.getAttribute('type') || '',
              name: el.getAttribute('name') || '',
              id: el.id || '',
              placeholder: el.getAttribute('placeholder') || '',
              value: el.tagName === 'SELECT' ? '' : (el.getAttribute('value') || ''),
              text: (el.innerText || '').trim().slice(0, 120),
              options: el.tagName === 'SELECT' ? [...el.options].map((o) => ({value: o.value, text: o.text.trim()})) : []
            }))"""
        )
        (self.debug_dir / f"{safe}-controls.json").write_text(
            json.dumps({"url": page.url, "controls": controls}, indent=2),
            encoding="utf-8",
        )

    async def submit(self, people: list[Person]) -> CheckoutResult:
        run_started = time.time()
        timings: dict[str, int] = {}

        if not people:
            return CheckoutResult(success=False, message="No people to order")

        if self.dry_run:
            if self.ui:
                self.ui.phase("Dry run")
                for i, p in enumerate(people, 1):
                    self.ui.progress(i, len(people), p.display_name)
                    self.ui.ok(f"Would order {p.display_name} ({p.state})")
            results = [
                OrderResult(
                    person=p,
                    success=True,
                    message=f"[dry-run] Would order {p.display_name} ({p.state})",
                    state_selected=p.state_variant or p.state,
                )
                for p in people
            ]
            return CheckoutResult(
                success=True,
                message="Dry run complete — no network requests",
                submitted_ids=[p.display_name for p in people],
                discount_code=self.discount_code,
                cart_count=len(people),
                order_results=results,
                dry_run=True,
                transport=self.transport,
                checkout_attempted=self.checkout,
                checkout_completed=not self.checkout,
                checkout_message="Dry run complete — checkout not launched" if self.checkout else "",
                shipping=self.shipping if self.checkout else None,
                events=self.ui.events if self.ui else [],
            )

        if self.transport == "http":
            from .http_submit import submit_http

            result = await submit_http(self, people)
            if self.use_cache and not self.dry_run and result.success:
                cache = OrderCache(self.cache_dir)
                result.cache_path = str(cache.save(result.to_dict()))
            if self.ui:
                if result.success:
                    self.ui.ok("Done")
                else:
                    self.ui.fail("Run finished with errors")
            return result

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return CheckoutResult(
                success=False,
                message="playwright not installed. Run: pip install playwright && playwright install chromium",
            )

        results: list[OrderResult] = []
        proxy: ProxyConfig | None = None
        try:
            proxy = await self._resolve_proxy()
            if self.proxies and not proxy and self.auto_proxy:
                return CheckoutResult(
                    success=False,
                    message="No working proxy found for idgod.ph",
                    probe_results=self._probe_results,
                    discount_code=self.discount_code,
                )

            async with async_playwright() as pw:
                if self.ui:
                    self.ui.phase("Browser")
                    self.ui.step("Launching Chromium…")
                try:
                    browser = await self._launch_browser(pw)
                except Exception as e:
                    return CheckoutResult(
                        success=False,
                        message=(
                            f"Browser launch failed: {e}. "
                            "Run from Terminal.app (not Cursor agent shell), or try --headed."
                        ),
                        proxy_used=proxy.display if proxy else "direct",
                        probe_results=self._probe_results,
                        discount_code=self.discount_code,
                        checkout_attempted=self.checkout,
                    )
                context = await browser.new_context(user_agent=USER_AGENT, viewport={"width": 1400, "height": 900})
                page = await context.new_page()
                page.set_default_timeout(self.timeout_ms)
                if self.ui:
                    self.ui.ok("Browser ready")

                try:
                    if self.ui:
                        self.ui.phase("Order forms")
                        self.ui.step(f"Navigating to {ORDER_URL}")
                    resp = await page.goto(ORDER_URL, wait_until="domcontentloaded", timeout=self.timeout_ms)
                    if not resp or not resp.ok:
                        return CheckoutResult(
                            success=False,
                            message=f"Failed to load order page (status={resp.status if resp else 'none'})",
                            proxy_used=proxy.display if proxy else "direct",
                            probe_results=self._probe_results,
                            discount_code=self.discount_code,
                        )

                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await page.wait_for_timeout(1500)
                    if self.ui:
                        self.ui.ok("Order page loaded")

                    for i, person in enumerate(people):
                        if self.ui:
                            self.ui.progress(i + 1, len(people), person.display_name)
                        if i > 0:
                            await page.goto(ORDER_URL, wait_until="domcontentloaded")
                            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                            await page.wait_for_timeout(1000)
                        is_last = i == len(people) - 1
                        result = await self._fill_person(page, person, checkout=is_last)
                        results.append(result)
                        if not result.success:
                            break

                    failed = [r for r in results if not r.success]
                    if failed:
                        return CheckoutResult(
                            success=False,
                            message=failed[0].message,
                            order_results=results,
                            discount_code=self.discount_code,
                            proxy_used=proxy.display if proxy else "direct",
                            probe_results=self._probe_results,
                        )

                    # Ensure we're on cart/checkout to read totals
                    ok_cart, cart_msg = await _ensure_cart_checkout_page(
                        page, timeout_ms=max(self.timeout_ms, 90000)
                    )
                    if not ok_cart:
                        return CheckoutResult(
                            success=False,
                            message=cart_msg,
                            order_results=results,
                            discount_code=self.discount_code,
                            proxy_used=proxy.display if proxy else "direct",
                            probe_results=self._probe_results,
                            checkout_attempted=self.checkout,
                        )

                    await self._write_debug_dump(page, "cart-before-checkout")
                    fill_meta = CheckoutFillMeta(completed=False, message="", filled=[], missing=[])
                    discount_applied = False
                    discount_msg = "Coupon not applied"
                    savings = None
                    if self.checkout:
                        fill_meta = await self._fill_checkout(page)
                        if fill_meta.total_before_discount is None:
                            total_before, _ = await self._read_totals(page)
                            fill_meta.total_before_discount = total_before
                        await page.wait_for_load_state("domcontentloaded")
                        await page.wait_for_timeout(1000)
                        await self._write_debug_dump(page, "cart-after-checkout")
                    else:
                        discount_applied, discount_msg = await self._apply_discount(page)
                        fill_meta.total_before_discount, _ = await self._read_totals(page)
                        fill_meta.total_after_discount = fill_meta.total_before_discount

                    total, cart_count = await self._read_totals(page)
                    if fill_meta.total_before_discount is None:
                        fill_meta.total_before_discount = total

                    payment_url = page.url
                    payment_details = PaymentDetails(invoice_url=payment_url)
                    if fill_meta.completed and (
                        self.fetch_payment or "btcpay" in payment_url.lower()
                    ):
                        if self.ui:
                            self.ui.phase("Payment")
                            self.ui.step("Fetching BTCPay invoice…")
                        payment_details = await fetch_btcpay_from_page(
                            page, timeout_ms=self.timeout_ms
                        )
                        if payment_details.invoice_url and not payment_url.startswith(
                            "https://btcpay"
                        ):
                            payment_url = payment_details.invoice_url

                    if self.discount_code and fill_meta.total_before_discount is not None:
                        from .http_forms import finalize_coupon_result, parse_fiat_amount

                        invoice_fiat = payment_details.total_fiat if payment_details.populated else ""
                        discount_applied, discount_msg, savings, invoice_total = (
                            finalize_coupon_result(
                                self.discount_code,
                                fill_meta.total_before_discount,
                                invoice_fiat,
                            )
                        )
                        if discount_applied and invoice_total is not None:
                            fill_meta.total_after_discount = invoice_total
                        if self.ui and payment_details.populated:
                            if discount_applied:
                                self.ui.ok(discount_msg)
                            elif self.require_coupon and fill_meta.completed:
                                self.ui.fail(discount_msg or "Coupon not reflected on invoice")
                            self.ui.ok(f"Invoice {payment_details.invoice_id or payment_url}")

                    body_text = await page.inner_text("body")
                    if payment_details.populated:
                        pay_lines = payment_details.summary_lines()
                    else:
                        pay_lines = [
                            ln.strip()
                            for ln in body_text.splitlines()
                            if re.search(
                                r"pay|bitcoin|litecoin|wallet|email|order|total", ln, re.I
                            )
                            and 5 < len(ln.strip()) < 200
                        ][:12]

                    submitted = [r.person.display_name for r in results if r.success]
                    invoice_total = fill_meta.total_after_discount or total
                    price_per = (invoice_total / len(submitted)) if invoice_total and submitted else None
                    elapsed_ms = int((time.time() - run_started) * 1000)
                    timings["total_ms"] = elapsed_ms
                    if fill_meta.captcha_solve_time_ms:
                        timings["captcha_ms"] = fill_meta.captcha_solve_time_ms

                    tor_mode = self._tor_mgr.mode if self.use_tor else ""

                    coupon_blocked = (
                        self.checkout_submit
                        and fill_meta.completed
                        and self.require_coupon
                        and bool(self.discount_code)
                        and not discount_applied
                        and payment_details.populated
                    )
                    if coupon_blocked and not fill_meta.message:
                        fill_meta.message = (
                            discount_msg or f"Coupon '{self.discount_code}' required but not applied"
                        )
                    if self.checkout and not fill_meta.completed:
                        result_message = fill_meta.message or discount_msg or "Checkout incomplete"
                    elif coupon_blocked:
                        result_message = discount_msg or f"Coupon '{self.discount_code}' not on invoice"
                    elif discount_applied:
                        result_message = discount_msg
                    else:
                        result_message = "Order submitted to cart/checkout"

                    result = CheckoutResult(
                        success=all(r.success for r in results)
                        and (not self.checkout_submit or fill_meta.completed)
                        and not coupon_blocked,
                        message=result_message,
                        submitted_ids=submitted,
                        payment_url=payment_url,
                        payment_info="\n".join(pay_lines),
                        payment_details=payment_details if payment_details.populated else None,
                        total_price=(
                            parse_fiat_amount(payment_details.total_fiat)
                            if payment_details.populated and payment_details.total_fiat
                            else (fill_meta.total_after_discount or total)
                        ),
                        total_before_discount=fill_meta.total_before_discount,
                        total_after_discount=fill_meta.total_after_discount,
                        discount_savings=savings,
                        price_per_id=price_per,
                        discount_code=self.discount_code,
                        discount_applied=discount_applied,
                        cart_count=cart_count or len(submitted),
                        order_results=results,
                        proxy_used=proxy.display if proxy else "direct",
                        probe_results=self._probe_results,
                        checkout_attempted=self.checkout,
                        checkout_completed=fill_meta.completed,
                        checkout_message=fill_meta.message,
                        checkout_fields=fill_meta.filled,
                        checkout_missing_fields=fill_meta.missing,
                        captcha_solver=fill_meta.captcha_solver,
                        captcha_solved=fill_meta.captcha_solved,
                        captcha_solve_time_ms=fill_meta.captcha_solve_time_ms,
                        captcha_attempts_used=fill_meta.captcha_attempts_used,
                        elapsed_ms=elapsed_ms,
                        tor_mode=tor_mode,
                        transport="browser",
                        input_file=self.input_file,
                        timings=timings,
                        shipping=self.shipping if self.checkout else None,
                        events=self.ui.events if self.ui else [],
                    )

                    if self.use_cache and not self.dry_run:
                        cache = OrderCache(self.cache_dir)
                        result.cache_path = str(cache.save(result.to_dict()))

                    if self.ui:
                        if result.success:
                            self.ui.ok("Done")
                        else:
                            self.ui.fail("Run finished with errors")

                    return result
                except Exception as e:
                    return CheckoutResult(
                        success=False,
                        message=str(e),
                        order_results=results,
                        discount_code=self.discount_code,
                        proxy_used=proxy.display if proxy else "direct",
                        probe_results=self._probe_results,
                    )
                finally:
                    await browser.close()
        finally:
            self._tor_mgr.stop()
