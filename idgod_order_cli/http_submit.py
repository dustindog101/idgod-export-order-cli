"""HTTP-only order submission (no Playwright)."""

from __future__ import annotations

import asyncio
import re
import tempfile
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urljoin, urlparse

import httpx

from .btcpay import PaymentDetails, fetch_btcpay_http, parse_btcpay_html
from .cache import OrderCache
from .captcha import (
    CAPTCHA_LEN_MAX,
    CAPTCHA_LEN_MIN,
    CaptchaSolverError,
    best_captcha_guess,
    normalize_captcha_text,
    solve_captcha_image,
    unpack_captcha_result,
)
from .http_client import IdGodHttpSession
from .http_forms import (
    ORDER_FORM_ID,
    captcha_hash_from_image_url,
    captcha_image_url,
    detect_coupon_rejection,
    coupon_savings_message,
    extract_csrf,
    finalize_coupon_result,
    parse_fiat_amount,
    extract_order_error,
    find_form,
    form_action_url,
    form_post_data,
    input_value,
    parse_forms,
    read_cart_total,
    select_by_name,
    select_value_by_label,
    select_value_contains,
)
from .models import CheckoutFillMeta, CheckoutResult, OrderResult, Person
from .orderer import (
    CART_URL,
    DEFAULT_SHIPPING_VALUE,
    ORDER_URL,
    USER_AGENT,
    _extract_order_error,
    _prepare_upload_image,
    fetch_vendor_image_bytes,
)
from .selectors import PAYMENT_LABELS, SHIPPING_ALIASES
from .states import (
    expand_state_name,
    estimate_price,
    map_eye_color,
    map_hair_color,
    map_sex,
    parse_height,
    pick_state_option,
    variant_from_product_id,
    StateOption,
)

if TYPE_CHECKING:
    from .orderer import IdGodOrderer

UploadFile = tuple[str, bytes, str]
ImageCache = dict[str, UploadFile]


async def _download_upload_file(
    orderer: IdGodOrderer,
    source: str,
    fallback: str,
    cache: ImageCache,
) -> UploadFile | None:
    src = (source or "").strip()
    if not src:
        if fallback:
            src = fallback
        else:
            return None
    if src in cache:
        return cache[src]

    if src.startswith(("http://", "https://")):
        try:
            content = await fetch_vendor_image_bytes(src)
            suffix = Path(urlparse(src).path).suffix or ".jpg"
            tmp = Path(tempfile.mktemp(suffix=suffix))
            tmp.write_bytes(content)
            prepared = _prepare_upload_image(tmp)
            item: UploadFile = (
                prepared.name,
                prepared.read_bytes(),
                "image/jpeg",
            )
            cache[src] = item
            return item
        except Exception:
            if fallback and fallback != src:
                return await _download_upload_file(orderer, fallback, "", cache)
            raise

    p = Path(src).expanduser()
    prepared = _prepare_upload_image(p)
    item = (prepared.name, prepared.read_bytes(), "image/jpeg")
    cache[src] = item
    return item


async def _prefetch_uploads(
    orderer: IdGodOrderer,
    people: list[Person],
    cache: ImageCache,
) -> None:
    items: list[tuple[str, str]] = []
    for person in people:
        items.append((person.photo, orderer.fallback_photo))
        items.append((person.signature, orderer.fallback_signature))

    async def _one(src: str, fb: str) -> None:
        if not src and not fb:
            return
        item = await _download_upload_file(orderer, src, fb, cache)
        if item:
            if src:
                cache[src] = item
            if fb:
                cache[fb] = item

    if items:
        unique_items = list(dict.fromkeys(items))
        await asyncio.gather(*[_one(src, fb) for src, fb in unique_items])


def _files_for_person(
    person: Person,
    orderer: IdGodOrderer,
    cache: ImageCache,
) -> dict[str, UploadFile]:
    files: dict[str, UploadFile] = {}
    photo_key = person.photo or orderer.fallback_photo
    if photo_key and photo_key in cache:
        files["picture"] = cache[photo_key]
    sig_key = person.signature or orderer.fallback_signature
    if sig_key and sig_key in cache:
        files["signature"] = cache[sig_key]
    return files


def _state_options_from_form(form: dict[str, Any]) -> list[StateOption]:
    sel = select_by_name(form, "state")
    if not sel:
        return []
    options: list[StateOption] = []
    for opt in sel.get("options", []):
        label = (opt.get("label") or "").strip()
        value = opt.get("value", "")
        if label and value:
            options.append(StateOption(label=label, price=estimate_price(label)))
    return options


def _state_value(form: dict[str, Any], chosen_label: str) -> str:
    sel = select_by_name(form, "state")
    if not sel:
        return ""
    for opt in sel.get("options", []):
        if chosen_label.lower() in (opt.get("label") or "").lower():
            return opt.get("value", "")
    return ""


async def _build_order_fields(
    orderer: IdGodOrderer,
    person: Person,
    form: dict[str, Any],
    csrf: str,
) -> tuple[dict[str, Any], str | None]:
    state_options = _state_options_from_form(form)
    state_name = expand_state_name(person.state)
    variant = (
        person.state_variant
        or orderer.state_variants.get(state_name, "")
        or orderer.state_variants.get(person.state, "")
        or variant_from_product_id(person.product_id)
    )
    chosen, note = pick_state_option(
        state_name,
        state_options,
        variant=variant,
        cheapest=orderer.cheapest_state,
    )
    if chosen is None:
        return {}, note or "State not found"

    feet, inches = parse_height(person.height or "5'6\"")
    selects = {s.get("name"): s for s in form.get("selects", []) if s.get("name")}

    fields: dict[str, Any] = {}
    for inp in form.get("inputs", []):
        if inp.get("type") == "hidden" and inp.get("name"):
            fields[inp["name"]] = inp.get("value", "")

    fields.update(
        {
            "csrfmiddlewaretoken": csrf,
            "first_name": person.first_name,
            "middle_name": person.middle_name or "",
            "last_name": person.last_name,
            "date_of_birth": person.dob,
            "state": _state_value(form, chosen.label),
            "height_feet": feet,
            "height_inches": inches,
            "weight": person.weight or "130",
            "eyes": select_value_by_label(selects.get("eyes"), map_eye_color(person.eye_color or "Brown")),
            "hair": select_value_by_label(selects.get("hair"), map_hair_color(person.hair_color or "Brown")),
            "gender": select_value_by_label(selects.get("gender"), map_sex(person.sex or "Female")),
            "address1": person.street or "123 Main St",
            "address2": "",
            "city": person.city,
            "zip": person.zip,
        }
    )
    if person.issue_date:
        fields["custom_license_number"] = person.issue_date
    return fields, chosen.label


def _overlay_checkout_fields(
    orderer: IdGodOrderer,
    form: dict[str, Any],
    data: dict[str, str],
) -> None:
    shipping = orderer.shipping
    if not shipping.is_local_delivery:
        data.update(
            {
                "name": shipping.name,
                "address": shipping.street,
                "city": shipping.city,
                "state": shipping.state,
                "zip": shipping.zip,
                "country": shipping.country or "USA",
            }
        )
    data["email"] = shipping.email

    pay_label = orderer._resolve_payment_label() or PAYMENT_LABELS.get("bitcoin", "Bitcoin")
    pay_val = select_value_by_label(select_by_name(form, "payment_method"), pay_label)
    if pay_val:
        data["payment_method"] = pay_val

    ship_label = orderer._resolve_shipping_label()
    pri_sel = select_by_name(form, "priority")
    ship_val = select_value_contains(pri_sel, ship_label) if ship_label else ""
    if ship_val:
        data["priority"] = ship_val
    elif not (data.get("priority") or "").strip():
        data["priority"] = DEFAULT_SHIPPING_VALUE

    if orderer.discount_code:
        data["coupon"] = orderer.discount_code

    phone = (shipping.phone or "").strip()
    if phone:
        data["phone_number"] = phone
    elif "phone_number" in data and not data["phone_number"].strip():
        data["phone_number"] = " "


def _strip_captcha_fields(data: dict[str, str]) -> dict[str, str]:
    return {k: v for k, v in data.items() if not k.startswith("captcha")}


def _build_finish_post_data(
    orderer: IdGodOrderer,
    form: dict[str, Any],
    cart_html: str,
    *,
    captcha_hash: str,
    captcha_guess: str,
) -> dict[str, str]:
    data = _strip_captcha_fields(form_post_data(form, cart_html))
    data["csrfmiddlewaretoken"] = extract_csrf(cart_html, form)
    data["captcha_0"] = captcha_hash
    data["captcha_1"] = captcha_guess
    data["action"] = "finish"
    _overlay_checkout_fields(orderer, form, data)
    if orderer.discount_code:
        data["coupon"] = orderer.discount_code
    return data


async def _sync_cart_coupon_http(
    session: IdGodHttpSession,
    orderer: IdGodOrderer,
    cart_html: str,
    form: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    """UPDATE cart on server so coupon/shipping persist before FINISH ORDER."""
    html, new_form, _, _ = await _cart_update_http(
        session, orderer, cart_html, form, include_coupon=True
    )
    return html, new_form


async def _cart_update_http(
    session: IdGodHttpSession,
    orderer: IdGodOrderer,
    cart_html: str,
    form: dict[str, Any],
    *,
    include_coupon: bool = True,
) -> tuple[str, dict[str, Any], float | None, str | None]:
    """POST cart UPDATE with full form state; optionally omit coupon for a 2-step apply."""
    csrf = extract_csrf(cart_html, form)
    data = _strip_captcha_fields(form_post_data(form, cart_html))
    data["csrfmiddlewaretoken"] = csrf
    saved_code = orderer.discount_code
    if not include_coupon:
        orderer.discount_code = ""
    try:
        _overlay_checkout_fields(orderer, form, data)
    finally:
        orderer.discount_code = saved_code
    if include_coupon and saved_code:
        data["coupon"] = saved_code
    data["action"] = "update"
    post_url = form_action_url(form, CART_URL)
    resp = await session.post_form(post_url, referer=CART_URL, data=data)
    body = resp.text
    total, _, _ = read_cart_total(body)
    coupon_err = detect_coupon_rejection(body, saved_code)
    forms = parse_forms(body)
    new_form = find_form(forms, ORDER_FORM_ID) or form
    return body, new_form, total, coupon_err


async def _apply_coupon_http(
    session: IdGodHttpSession,
    orderer: IdGodOrderer,
    cart_html: str,
    form: dict[str, Any],
) -> tuple[str, dict[str, Any], float | None, float | None, str | None]:
    """Apply coupon via one UPDATE (same as Playwright: all fields + coupon together)."""
    total_before, _, _ = read_cart_total(cart_html)
    if not orderer.discount_code:
        return cart_html, form, total_before, total_before, None

    html, new_form, total_after, err = await _cart_update_http(
        session, orderer, cart_html, form, include_coupon=True
    )
    return html, new_form, total_before, total_after, err


async def _add_person_http(
    session: IdGodHttpSession,
    orderer: IdGodOrderer,
    person: Person,
    *,
    checkout: bool,
    cache: ImageCache,
    order_ctx: dict[str, Any],
    verify_cart: bool,
) -> OrderResult:
    if order_ctx.get("form") and order_ctx.get("csrf"):
        form = order_ctx["form"]
        csrf = order_ctx["csrf"]
    else:
        _, html, forms = await session.get_page(ORDER_URL)
        form = find_form(forms, ORDER_FORM_ID)
        if not form:
            return OrderResult(person=person, success=False, message="order-form not found")
        csrf = extract_csrf(html, form)
        order_ctx["form"] = form
        order_ctx["csrf"] = csrf

    if not csrf:
        return OrderResult(person=person, success=False, message="CSRF token missing")

    fields, state_label = await _build_order_fields(orderer, person, form, csrf)
    if not fields:
        return OrderResult(person=person, success=False, message=state_label or "Form build failed")

    if orderer.ui:
        orderer.ui.detail(f"HTTP submit: {person.display_name}")

    try:
        if person.photo or orderer.fallback_photo:
            await _download_upload_file(
                orderer, person.photo, orderer.fallback_photo, cache
            )
        if person.signature or orderer.fallback_signature:
            await _download_upload_file(
                orderer, person.signature, orderer.fallback_signature, cache
            )
    except Exception as e:
        return OrderResult(person=person, success=False, message=str(e))

    files = _files_for_person(person, orderer, cache)
    if "picture" not in files:
        return OrderResult(person=person, success=False, message="Photo upload missing")

    fields["action"] = "2" if checkout else "1"
    post_url = form_action_url(form, ORDER_URL)
    resp = await session.post_form(post_url, referer=ORDER_URL, data=fields, files=files)
    body = resp.text

    if resp.status_code == 403 and "csrf" in body.lower():
        order_ctx.pop("form", None)
        order_ctx.pop("csrf", None)
        return await _add_person_http(
            session, orderer, person,
            checkout=checkout, cache=cache, order_ctx=order_ctx, verify_cart=verify_cart,
        )

    err = extract_order_error(body)
    if err:
        return OrderResult(
            person=person,
            success=False,
            message=err,
            state_selected=state_label,
        )

    if verify_cart:
        _, cart_html, _ = await session.get_page(CART_URL)
        total, count, empty = read_cart_total(cart_html)
        if empty or not count:
            return OrderResult(
                person=person,
                success=False,
                message=_extract_order_error(body) or "Add-to-cart failed — cart still empty",
                state_selected=state_label,
            )
        if checkout and not re.search(r"id_email|id_name", cart_html, re.I):
            return OrderResult(
                person=person,
                success=False,
                message="Checkout redirect but cart form missing",
                state_selected=state_label,
            )

    return OrderResult(
        person=person,
        success=True,
        message=f"HTTP add {'checkout' if checkout else 'cart'} OK",
        state_selected=state_label,
    )


async def _apply_discount_http(session: IdGodHttpSession, orderer: IdGodOrderer) -> tuple[bool, str]:
    _, cart_html, forms = await session.get_page(CART_URL)
    form = find_form(forms, ORDER_FORM_ID)
    if not form or not orderer.discount_code:
        return False, "No coupon field"
    _, _, before, after, coupon_err = await _apply_coupon_http(session, orderer, cart_html, form)
    if coupon_err:
        return False, coupon_err
    applied, msg, _ = coupon_savings_message(orderer.discount_code, before, after)
    if applied:
        return True, msg
    return False, msg


async def _checkout_http(
    session: IdGodHttpSession,
    orderer: IdGodOrderer,
) -> tuple[CheckoutFillMeta, httpx.Response | None]:
    if orderer.ui:
        orderer.ui.phase("Checkout")
        orderer.ui.step("Filling shipping & payment")

    shipping = orderer.shipping
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
    missing_values = [k for k, v in required.items() if not v]
    if missing_values:
        msg = f"Missing checkout values: {', '.join(missing_values)}"
        return CheckoutFillMeta(completed=False, message=msg, missing=missing_values), None

    _, cart_html, forms = await session.get_page(CART_URL)
    form = find_form(forms, ORDER_FORM_ID)
    if not form:
        return CheckoutFillMeta(completed=False, message="Cart checkout form not found"), None

    filled: list[str] = []

    if not shipping.is_local_delivery:
        filled.extend(["name", "address", "city", "state", "zip", "country"])
    filled.append("email")
    filled.append("payment_method")
    filled.append("shipping_method")

    if orderer.discount_code:
        filled.append("coupon")
        if orderer.ui:
            orderer.ui.detail(f"Applying coupon {orderer.discount_code}")

    if orderer.ui:
        orderer.ui.step("Updating cart")
    cart_html, form, total_before, total_after, coupon_err = await _apply_coupon_http(
        session, orderer, cart_html, form
    )
    filled.append("cart_update")

    if coupon_err and orderer.ui:
        orderer.ui.warn(coupon_err)

    discount_applied, discount_msg, savings = coupon_savings_message(
        orderer.discount_code, total_before, total_after
    )
    if orderer.discount_code and orderer.ui:
        if discount_applied:
            orderer.ui.ok(discount_msg)
        elif coupon_err:
            orderer.ui.fail(f"Coupon '{orderer.discount_code}' rejected")
        else:
            orderer.ui.detail(discount_msg)

    finish_resp: httpx.Response | None = None
    captcha_solver = ""
    captcha_solved = False
    captcha_solve_time_ms = 0
    captcha_attempts_used = 0

    if orderer.checkout_submit:
        if orderer.captcha_solver == "manual":
            return (
                CheckoutFillMeta(
                    completed=False,
                    message="Captcha required — HTTP mode needs --captcha-solver ppllocr|2captcha",
                    filled=filled,
                    missing=["captcha"],
                    total_before_discount=total_before,
                    total_after_discount=total_after,
                ),
                None,
            )

        ok, captcha_msg, captcha_solver, captcha_solve_time_ms, captcha_attempts_used = (
            await _solve_captcha_http(session, orderer, form, cart_html)
        )
        if not ok:
            return (
                CheckoutFillMeta(
                    completed=False,
                    message=captcha_msg,
                    filled=filled,
                    missing=["captcha"],
                    captcha_solver=captcha_solver,
                    captcha_solve_time_ms=captcha_solve_time_ms,
                    captcha_attempts_used=captcha_attempts_used,
                    total_before_discount=total_before,
                    total_after_discount=total_after,
                ),
                None,
            )
        captcha_solved = True
        filled.append("captcha")
        filled.append("checkout_submit")
        finish_resp = getattr(orderer, "_http_finish_response", None)

    completed = orderer.checkout_submit and captcha_solved
    message = "Checkout fields filled via HTTP"
    if completed and finish_resp:
        message = f"Order finished; URL: {finish_resp.url}"

    return (
        CheckoutFillMeta(
            completed=completed,
            message=message,
            filled=filled,
            missing=[],
            captcha_solver=captcha_solver,
            captcha_solved=captcha_solved,
            captcha_solve_time_ms=captcha_solve_time_ms,
            captcha_attempts_used=captcha_attempts_used,
            total_before_discount=total_before,
            total_after_discount=total_after,
        ),
        finish_resp,
    )


async def _solve_captcha_http(
    session: IdGodHttpSession,
    orderer: IdGodOrderer,
    form: dict[str, Any],
    cart_html: str,
) -> tuple[bool, str, str, int, int]:
    started = time.time()
    captcha_mode = orderer.captcha_solver
    if captcha_mode in ("ppllocr", "ddddocr"):
        captcha_mode = "auto"

    captcha_hash = input_value(form, "captcha_0")
    last_error = ""
    solver_used = ""
    max_attempts = orderer.captcha_attempts

    if orderer.ui:
        orderer.ui.phase("Captcha")

    for attempt in range(1, max_attempts + 1):
        if orderer.ui:
            orderer.ui.step(f"Attempt {attempt}/{max_attempts}: reading captcha image")

        img_url = captcha_image_url(cart_html, CART_URL)
        if not img_url and captcha_hash:
            img_url = urljoin(CART_URL, f"/captcha/image/{captcha_hash}/")
        if not img_url:
            refreshed = await session.refresh_captcha()
            if refreshed:
                captcha_hash = refreshed["key"]
                img_url = refreshed["image_url"]
        if not img_url:
            last_error = "Captcha image URL not found"
            if orderer.ui:
                orderer.ui.warn(last_error)
            continue

        # Pin hash to the image we OCR. Cart UPDATE rotates captcha — never sync coupon here.
        image_captcha_hash = captcha_hash_from_image_url(img_url) or captcha_hash

        try:
            image_bytes = await session.get_bytes(img_url)
            if len(image_bytes) < 32:
                raise CaptchaSolverError("Captcha image too small")
            debug_path = await orderer._save_captcha_debug(image_bytes, f"attempt-{attempt}")
            result = await solve_captcha_image(
                image_bytes,
                mode=captcha_mode,
                api_key=orderer.twocaptcha_key,
            )
            guess, raw_text, solver_used, votes, reads = unpack_captcha_result(result)
        except CaptchaSolverError as e:
            last_error = str(e)
            if orderer.ui:
                orderer.ui.warn(last_error)
            refreshed = await session.refresh_captcha()
            if refreshed:
                captcha_hash = refreshed["key"]
                cart_html = (await session.get_page(CART_URL))[1]
            continue

        if not guess:
            last_error = f"OCR returned empty captcha text (saved {debug_path})"
            if orderer.ui:
                orderer.ui.warn(last_error)
            continue

        raw_len = len(normalize_captcha_text(raw_text))
        if raw_len < CAPTCHA_LEN_MIN or raw_len > CAPTCHA_LEN_MAX:
            if orderer.ui:
                orderer.ui.detail(f"OCR '{raw_text}' → trimmed '{guess}'")
        elif orderer.ui:
            orderer.ui.detail(
                f"OCR guess '{guess}' ({solver_used}, {votes} vote(s), {reads} reads)"
            )

        finish_data = _build_finish_post_data(
            orderer,
            form,
            cart_html,
            captcha_hash=image_captcha_hash,
            captcha_guess=guess,
        )

        post_url = form_action_url(form, CART_URL)
        resp = await session.post_form(post_url, referer=CART_URL, data=finish_data)
        body = resp.text
        if re.search(r"invalid captcha|incorrect captcha|captcha.*invalid", body, re.I):
            last_error = f"Captcha rejected for '{guess}' (raw OCR: {raw_text})"
            if orderer.ui:
                orderer.ui.warn(f"Rejected '{guess}' — refreshing")
            refreshed = await session.refresh_captcha()
            if refreshed:
                captcha_hash = refreshed["key"]
            _, cart_html, forms = await session.get_page(CART_URL)
            form = find_form(forms, ORDER_FORM_ID) or form
            captcha_hash = input_value(form, "captcha_0") or captcha_hash
            continue

        if "btcpay" in str(resp.url).lower() or extract_order_error(body):
            if extract_order_error(body):
                last_error = extract_order_error(body)
                continue
            solve_ms = int((time.time() - started) * 1000)
            orderer._http_finish_response = resp
            if orderer.ui:
                orderer.ui.ok(f"Captcha solved: {guess} ({solver_used}, {solve_ms}ms)")
            return True, f"Captcha solved: {guess}", solver_used, solve_ms, attempt

        if input_value(find_form(parse_forms(body), ORDER_FORM_ID) or {}, "captcha_1") == "":
            solve_ms = int((time.time() - started) * 1000)
            orderer._http_finish_response = resp
            if orderer.ui:
                orderer.ui.ok(f"Captcha solved: {guess} ({solver_used}, {solve_ms}ms)")
            return True, f"Captcha solved: {guess}", solver_used, solve_ms, attempt

        last_error = f"Captcha unclear result for '{guess}'"
        if orderer.ui:
            orderer.ui.warn(last_error)
        refreshed = await session.refresh_captcha()
        if refreshed:
            captcha_hash = refreshed["key"]
        _, cart_html, forms = await session.get_page(CART_URL)
        form = find_form(forms, ORDER_FORM_ID) or form
        captcha_hash = input_value(form, "captcha_0") or captcha_hash

    solve_ms = int((time.time() - started) * 1000)
    return False, last_error or "Captcha solving failed", solver_used, solve_ms, orderer.captcha_attempts


async def submit_http(orderer: IdGodOrderer, people: list[Person]) -> CheckoutResult:
    run_started = time.time()
    timings: dict[str, int] = {}
    orderer._http_finish_response = None

    proxy = await orderer._resolve_proxy()
    if orderer.proxies and not proxy and orderer.auto_proxy:
        return CheckoutResult(
            success=False,
            message="No working proxy found for idgod.ph",
            probe_results=orderer._probe_results,
            discount_code=orderer.discount_code,
        )

    results: list[OrderResult] = []
    image_cache: ImageCache = {}
    order_ctx: dict[str, Any] = {}
    try:
        async with IdGodHttpSession(proxy=proxy, timeout=orderer.timeout_ms / 1000) as session:
            if orderer.ui:
                orderer.ui.phase("Order")
                route = proxy.display if proxy else "direct"
                orderer.ui.ok(f"HTTP transport · {route}")

            url_count = sum(
                1
                for person in people
                for src in (person.photo, person.signature)
                if src and src.startswith(("http://", "https://"))
            )
            if orderer.ui:
                orderer.ui.phase("Images")
                orderer.ui.step(
                    f"Prefetching {url_count or 'local'} photo/signature file(s) (direct, not Tor)"
                )

            prefetch_started = time.time()
            await _prefetch_uploads(orderer, people, image_cache)
            timings["prefetch_images_ms"] = int((time.time() - prefetch_started) * 1000)
            if orderer.ui and timings["prefetch_images_ms"]:
                orderer.ui.ok(f"Images ready ({timings['prefetch_images_ms'] / 1000:.1f}s)")

            add_started = time.time()
            for i, person in enumerate(people):
                if orderer.ui:
                    orderer.ui.progress(i + 1, len(people), person.display_name)
                is_last = i == len(people) - 1
                result = await _add_person_http(
                    session,
                    orderer,
                    person,
                    checkout=is_last and orderer.checkout,
                    cache=image_cache,
                    order_ctx=order_ctx,
                    verify_cart=is_last,
                )
                results.append(result)
                if result.success and orderer.ui:
                    orderer.ui.ok(f"{person.display_name} · {result.state_selected or person.state}")
                if not result.success:
                    if orderer.ui:
                        orderer.ui.fail(result.message)
                    break
            timings["add_to_cart_ms"] = int((time.time() - add_started) * 1000)

            failed = [r for r in results if not r.success]
            if failed:
                return CheckoutResult(
                    success=False,
                    message=failed[0].message,
                    order_results=results,
                    discount_code=orderer.discount_code,
                    proxy_used=proxy.display if proxy else "direct",
                    probe_results=orderer._probe_results,
                    transport="http",
                    timings=timings,
                    elapsed_ms=int((time.time() - run_started) * 1000),
                )

            _, cart_html, _ = await session.get_page(CART_URL)
            total, cart_count, empty = read_cart_total(cart_html)
            if empty:
                return CheckoutResult(
                    success=False,
                    message="Cart is empty after HTTP submit",
                    order_results=results,
                    discount_code=orderer.discount_code,
                    proxy_used=proxy.display if proxy else "direct",
                    transport="http",
                )

            fill_meta = CheckoutFillMeta(completed=False, message="", filled=[], missing=[])
            finish_resp = None
            discount_applied = False
            discount_msg = "Coupon not applied"
            savings = None

            if orderer.checkout:
                checkout_started = time.time()
                fill_meta, finish_resp = await _checkout_http(session, orderer)
                timings["checkout_ms"] = int((time.time() - checkout_started) * 1000)
                if fill_meta.total_before_discount is None:
                    fill_meta.total_before_discount = total
                if finish_resp is None and orderer._http_finish_response is not None:
                    finish_resp = orderer._http_finish_response
            else:
                fill_meta.total_before_discount = total
                fill_meta.total_after_discount = total

            payment_url = str(finish_resp.url) if finish_resp else CART_URL
            payment_details = PaymentDetails(invoice_url=payment_url)
            if finish_resp and ("btcpay" in payment_url.lower() or orderer.fetch_payment):
                if orderer.ui:
                    orderer.ui.phase("Payment")
                    orderer.ui.step("Fetching BTCPay invoice…")
                payment_details = await fetch_btcpay_http(
                    session.client,
                    payment_url,
                    timeout=min(12.0, orderer.timeout_ms / 1000),
                )
                if not payment_details.invoice_url:
                    payment_details.invoice_url = payment_url
                if payment_details.invoice_url:
                    payment_url = payment_details.invoice_url
                if orderer.ui and payment_details.invoice_id:
                    orderer.ui.ok(f"Invoice {payment_details.invoice_id}")

            if orderer.discount_code and fill_meta.total_before_discount is not None:
                invoice_fiat = payment_details.total_fiat if payment_details.populated else ""
                discount_applied, discount_msg, savings, invoice_total = finalize_coupon_result(
                    orderer.discount_code,
                    fill_meta.total_before_discount,
                    invoice_fiat,
                )
                if discount_applied and invoice_total is not None:
                    fill_meta.total_after_discount = invoice_total
                if orderer.ui and invoice_fiat:
                    if discount_applied:
                        orderer.ui.ok(discount_msg)
                    elif orderer.require_coupon and fill_meta.completed:
                        orderer.ui.fail(discount_msg or "Coupon not reflected on invoice")
                elif orderer.discount_code and orderer.ui and fill_meta.completed:
                    orderer.ui.detail(
                        "Coupon entered — discount is confirmed from BTCPay invoice after checkout"
                    )

            if orderer.ui and fill_meta.completed:
                orderer.ui.ok("Done")

            pay_lines = (
                payment_details.summary_lines()
                if payment_details.populated
                else []
            )

            submitted = [r.person.display_name for r in results if r.success]
            invoice_total = fill_meta.total_after_discount or total
            price_per = (invoice_total / len(submitted)) if invoice_total and submitted else None
            elapsed_ms = int((time.time() - run_started) * 1000)
            timings["total_ms"] = elapsed_ms
            if fill_meta.captcha_solve_time_ms:
                timings["captcha_ms"] = fill_meta.captcha_solve_time_ms

            coupon_blocked = (
                orderer.checkout_submit
                and fill_meta.completed
                and orderer.require_coupon
                and bool(orderer.discount_code)
                and not discount_applied
                and payment_details.populated
            )
            if coupon_blocked and not fill_meta.message:
                fill_meta.message = discount_msg or f"Coupon '{orderer.discount_code}' required but not applied"

            if orderer.checkout and not fill_meta.completed:
                result_message = fill_meta.message or discount_msg or "Checkout incomplete"
            elif coupon_blocked:
                result_message = discount_msg or f"Coupon '{orderer.discount_code}' not on invoice"
            elif discount_applied:
                result_message = discount_msg
            else:
                result_message = "Order submitted via HTTP"

            return CheckoutResult(
                success=all(r.success for r in results)
                and (not orderer.checkout_submit or fill_meta.completed)
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
                discount_code=orderer.discount_code,
                discount_applied=discount_applied,
                cart_count=cart_count or len(submitted),
                order_results=results,
                proxy_used=proxy.display if proxy else "direct",
                probe_results=orderer._probe_results,
                checkout_attempted=orderer.checkout,
                checkout_completed=fill_meta.completed,
                checkout_message=fill_meta.message,
                checkout_fields=fill_meta.filled,
                checkout_missing_fields=fill_meta.missing,
                captcha_solver=fill_meta.captcha_solver,
                captcha_solved=fill_meta.captcha_solved,
                captcha_solve_time_ms=fill_meta.captcha_solve_time_ms,
                captcha_attempts_used=fill_meta.captcha_attempts_used,
                elapsed_ms=elapsed_ms,
                tor_mode=orderer._tor_mgr.mode if orderer.use_tor else "",
                transport="http",
                input_file=orderer.input_file,
                timings=timings,
                shipping=orderer.shipping if orderer.checkout else None,
                events=orderer.ui.events if orderer.ui else [],
            )
    finally:
        orderer._tor_mgr.stop()
