from __future__ import annotations

import re
import tempfile
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from .models import CheckoutResult, OrderResult, Person, ShippingInfo
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
    map_eye_color,
    map_hair_color,
    map_sex,
    parse_height,
    pick_state_option,
)

ORDER_URL = "https://www.idgod.ph/order"
CART_URL = "https://www.idgod.ph/cart"
DEFAULT_DISCOUNT = "hartlr"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


async def _resolve_image(
    source: str,
    fallback: str = "",
    proxy: ProxyConfig | None = None,
) -> Path:
    src = source.strip()
    if src.startswith(("http://", "https://")):
        try:
            client_kwargs: dict[str, Any] = {
                "follow_redirects": True,
                "timeout": 30,
                "headers": {"User-Agent": USER_AGENT},
            }
            if proxy:
                client_kwargs["proxy"] = proxy.to_httpx()
            async with httpx.AsyncClient(**client_kwargs) as client:
                resp = await client.get(src)
                resp.raise_for_status()
                suffix = Path(urlparse(src).path).suffix or ".jpg"
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
                tmp.write(resp.content)
                tmp.close()
                return Path(tmp.name)
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
    return p


def _parse_money(text: str) -> float | None:
    m = re.search(r"\$?\s*([\d,]+\.?\d*)", text.replace(",", ""))
    return float(m.group(1)) if m else None


class IdGodOrderer:
    def __init__(
        self,
        *,
        headless: bool = True,
        discount_code: str = DEFAULT_DISCOUNT,
        fallback_photo: str = "",
        fallback_signature: str = "",
        cheapest_state: bool = False,
        state_variants: dict[str, str] | None = None,
        dry_run: bool = False,
        timeout_ms: int = 60000,
        proxies: list[ProxyConfig] | None = None,
        use_tor: bool = False,
        auto_proxy: bool = True,
        checkout: bool = False,
        checkout_submit: bool = False,
        shipping: ShippingInfo | None = None,
        payment_method: str = "",
        shipping_method: str = "",
        debug_dir: str = "",
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
        self.shipping = shipping or ShippingInfo()
        self.payment_method = payment_method
        self.shipping_method = shipping_method
        self.debug_dir = Path(debug_dir).expanduser() if debug_dir else None
        self._tor_mgr = TorManager()
        self._active_proxy: ProxyConfig | None = None
        self._probe_results: list[dict] = []

    async def _resolve_proxy(self) -> ProxyConfig | None:
        if self.use_tor:
            self._active_proxy = self._tor_mgr.start()
            return self._active_proxy

        if not self.proxies:
            return None

        if not self.auto_proxy:
            self._active_proxy = self.proxies[0]
            return self._active_proxy

        working, results = await pick_working_proxy(self.proxies, ORDER_URL)
        self._probe_results = results
        self._active_proxy = working
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
        state_options = await self._get_state_options(page)
        variant = person.state_variant or self.state_variants.get(person.state, "")
        chosen, note = pick_state_option(
            person.state,
            state_options,
            variant=variant,
            cheapest=self.cheapest_state,
        )
        if chosen is None:
            return OrderResult(person=person, success=False, message=note)

        feet, inches = parse_height(person.height or "5'6\"")
        try:
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

            photo_path = await _resolve_image(person.photo, self.fallback_photo, self._active_proxy)
            await page.locator(SELECTORS["picture"]).set_input_files(str(photo_path))

            if person.signature or self.fallback_signature:
                sig_path = await _resolve_image(person.signature, self.fallback_signature, self._active_proxy)
                sig_loc = page.locator(SELECTORS["signature"])
                if await sig_loc.count():
                    await sig_loc.set_input_files(str(sig_path))

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

            try:
                async with page.expect_navigation(timeout=self.timeout_ms):
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
                # Fallback: direct click
                await submit.first.click()
                await page.wait_for_timeout(4000)

            await page.wait_for_load_state("domcontentloaded")
            await page.wait_for_timeout(1000)

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

    async def _fill_checkout(self, page) -> tuple[bool, str, list[str], list[str]]:
        shipping = self.shipping
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
            return False, f"Missing checkout values: {', '.join(missing_values)}", [], missing_values

        filled: list[str] = []
        missing: list[str] = []

        await self._fill_cart_field(page, "name", shipping.name, filled, missing)
        await self._fill_cart_field(page, "email", shipping.email, filled, missing)
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
                await coupon.fill(self.discount_code)
                filled.append("coupon")

        if self.checkout_submit:
            captcha = page.locator(CART_SELECTORS["captcha"])
            if await captcha.count() and await captcha.is_visible():
                missing.append("captcha")
                return (
                    False,
                    "Checkout blocked: captcha required — use --headed and complete FINISH ORDER manually",
                    filled,
                    missing,
                )
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
        else:
            update = page.locator(CART_BUTTONS["update"])
            if await update.count() and filled:
                try:
                    async with page.expect_navigation(timeout=self.timeout_ms):
                        await update.click()
                except Exception:
                    await update.click()
                    await page.wait_for_timeout(2500)
                filled.append("cart_update")

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
        elif missing:
            message = f"Checkout partially filled; missing: {', '.join(missing)}"
        return completed, message, filled, missing

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
        if not people:
            return CheckoutResult(success=False, message="No people to order")

        if self.dry_run:
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
                message="Dry run complete — no browser launched",
                submitted_ids=[p.display_name for p in people],
                discount_code=self.discount_code,
                cart_count=len(people),
                order_results=results,
                dry_run=True,
                checkout_attempted=self.checkout,
                checkout_completed=not self.checkout,
                checkout_message="Dry run complete — checkout not launched" if self.checkout else "",
                shipping=self.shipping if self.checkout else None,
            )

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
                browser = await self._launch_browser(pw)
                context = await browser.new_context(user_agent=USER_AGENT, viewport={"width": 1400, "height": 900})
                page = await context.new_page()
                page.set_default_timeout(self.timeout_ms)

                try:
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

                    for i, person in enumerate(people):
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
                    if CART_URL not in page.url:
                        await page.goto(CART_URL, wait_until="domcontentloaded")
                        await page.wait_for_timeout(2000)

                    await self._write_debug_dump(page, "cart-before-checkout")
                    checkout_completed = False
                    checkout_message = ""
                    checkout_fields: list[str] = []
                    checkout_missing: list[str] = []
                    discount_applied = False
                    discount_msg = ""
                    if self.checkout:
                        checkout_completed, checkout_message, checkout_fields, checkout_missing = (
                            await self._fill_checkout(page)
                        )
                        discount_applied = "coupon" in checkout_fields
                        discount_msg = (
                            f"Coupon '{self.discount_code}' saved with UPDATE"
                            if discount_applied
                            else f"Coupon not applied"
                        )
                        await page.wait_for_load_state("domcontentloaded")
                        await page.wait_for_timeout(1000)
                        await self._write_debug_dump(page, "cart-after-checkout")
                    else:
                        discount_applied, discount_msg = await self._apply_discount(page)
                    total, cart_count = await self._read_totals(page)
                    payment_url = page.url
                    body_text = await page.inner_text("body")
                    pay_lines = [
                        ln.strip()
                        for ln in body_text.splitlines()
                        if re.search(r"pay|bitcoin|litecoin|wallet|email|order|total", ln, re.I)
                        and 5 < len(ln.strip()) < 200
                    ][:12]

                    submitted = [r.person.display_name for r in results if r.success]
                    price_per = (total / len(submitted)) if total and submitted else None

                    return CheckoutResult(
                        success=True,
                        message=discount_msg if discount_applied else "Order submitted to cart/checkout",
                        submitted_ids=submitted,
                        payment_url=payment_url,
                        payment_info="\n".join(pay_lines),
                        total_price=total,
                        price_per_id=price_per,
                        discount_code=self.discount_code,
                        discount_applied=discount_applied,
                        cart_count=cart_count or len(submitted),
                        order_results=results,
                        proxy_used=proxy.display if proxy else "direct",
                        probe_results=self._probe_results,
                        checkout_attempted=self.checkout,
                        checkout_completed=checkout_completed,
                        checkout_message=checkout_message,
                        checkout_fields=checkout_fields,
                        checkout_missing_fields=checkout_missing,
                        shipping=self.shipping if self.checkout else None,
                    )
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
