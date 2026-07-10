"""HTTP-only order submission (no Playwright)."""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urljoin

import httpx

from .btcpay import PaymentDetails, parse_btcpay_html
from .cache import OrderCache
from .captcha import (
    CAPTCHA_LEN_MAX,
    CAPTCHA_LEN_MIN,
    CaptchaSolverError,
    best_captcha_guess,
    normalize_captcha_text,
    solve_captcha_image,
)
from .http_client import IdGodHttpSession
from .http_forms import (
    ORDER_FORM_ID,
    captcha_image_url,
    extract_csrf,
    extract_order_error,
    find_form,
    form_action_url,
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
    _extract_order_error,
    _prepare_upload_image,
    _resolve_image,
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

    fields: dict[str, Any] = {
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
    if person.issue_date:
        fields["custom_license_number"] = person.issue_date
    return fields, chosen.label


async def _add_person_http(
    session: IdGodHttpSession,
    orderer: IdGodOrderer,
    person: Person,
    *,
    checkout: bool,
) -> OrderResult:
    _, html, forms = await session.get_page(ORDER_URL)
    form = find_form(forms, ORDER_FORM_ID)
    if not form:
        return OrderResult(person=person, success=False, message="order-form not found")

    csrf = extract_csrf(html, form)
    if not csrf:
        return OrderResult(person=person, success=False, message="CSRF token missing")

    fields, state_label = await _build_order_fields(orderer, person, form, csrf)
    if not fields:
        return OrderResult(person=person, success=False, message=state_label or "Form build failed")

    if orderer.ui:
        orderer.ui.detail(f"HTTP submit: {person.display_name}")

    photo_path = await _resolve_image(
        person.photo, orderer.fallback_photo, orderer._active_proxy
    )
    files: dict[str, tuple[str, bytes, str]] = {
        "picture": (photo_path.name, photo_path.read_bytes(), "image/jpeg"),
    }
    if person.signature or orderer.fallback_signature:
        try:
            sig_path = await _resolve_image(
                person.signature, orderer.fallback_signature, orderer._active_proxy
            )
            files["signature"] = (sig_path.name, sig_path.read_bytes(), "image/jpeg")
        except Exception:
            pass

    fields["action"] = "2" if checkout else "1"
    post_url = form_action_url(form, ORDER_URL)
    resp = await session.post_form(post_url, referer=ORDER_URL, data=fields, files=files)
    body = resp.text
    err = extract_order_error(body)
    if err:
        return OrderResult(
            person=person,
            success=False,
            message=err,
            state_selected=state_label,
        )

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
    csrf = extract_csrf(cart_html, form)
    data: dict[str, Any] = {
        "csrfmiddlewaretoken": csrf,
        "coupon": orderer.discount_code,
        "action": "update",
    }
    post_url = form_action_url(form, CART_URL)
    resp = await session.post_form(post_url, referer=CART_URL, data=data)
    if re.search(r"invalid|not found|expired|does not exist", resp.text, re.I):
        return False, f"Discount code '{orderer.discount_code}' rejected"
    return True, f"Applied coupon '{orderer.discount_code}' on cart (HTTP UPDATE)"


async def _checkout_http(
    session: IdGodHttpSession,
    orderer: IdGodOrderer,
) -> tuple[CheckoutFillMeta, httpx.Response | None]:
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

    total_before, _, _ = read_cart_total(cart_html)
    csrf = extract_csrf(cart_html, form)
    filled: list[str] = []
    data: dict[str, Any] = {"csrfmiddlewaretoken": csrf}

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
        filled.extend(["name", "address", "city", "state", "zip", "country"])
    data["email"] = shipping.email
    filled.append("email")

    pay_label = orderer._resolve_payment_label() or PAYMENT_LABELS.get("bitcoin", "Bitcoin")
    pay_val = select_value_by_label(select_by_name(form, "payment_method"), pay_label)
    if not pay_val:
        pay_val = "0"
    data["payment_method"] = pay_val
    filled.append("payment_method")

    ship_label = orderer._resolve_shipping_label()
    pri_sel = select_by_name(form, "priority")
    ship_val = select_value_contains(pri_sel, ship_label) if ship_label else ""
    data["priority"] = ship_val or DEFAULT_SHIPPING_VALUE
    filled.append("shipping_method")

    if orderer.discount_code:
        data["coupon"] = orderer.discount_code
        filled.append("coupon")

    data["action"] = "update"
    post_url = form_action_url(form, CART_URL)
    await session.post_form(post_url, referer=CART_URL, data=data)
    filled.append("cart_update")

    _, cart_html, forms = await session.get_page(CART_URL)
    form = find_form(forms, ORDER_FORM_ID) or form
    total_after, _, _ = read_cart_total(cart_html)

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

    for attempt in range(1, orderer.captcha_attempts + 1):
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
            continue

        try:
            image_bytes = await session.get_bytes(img_url)
            if image_bytes[:8] != b"\x89PNG\r\n\x1a\n":
                raise CaptchaSolverError("Captcha bytes are not PNG")
            result = await solve_captcha_image(
                image_bytes,
                mode=captcha_mode,
                api_key=orderer.twocaptcha_key,
            )
            solver_used = result["solver"]
            raw_text = result.get("raw_text") or result["text"]
            guess = result.get("guess") or best_captcha_guess(raw_text)
        except CaptchaSolverError as e:
            last_error = str(e)
            refreshed = await session.refresh_captcha()
            if refreshed:
                captcha_hash = refreshed["key"]
                cart_html = (await session.get_page(CART_URL))[1]
            continue

        if not guess:
            last_error = "OCR returned empty captcha text"
            continue

        csrf = extract_csrf(cart_html, form)
        finish_data: dict[str, Any] = {
            "csrfmiddlewaretoken": csrf,
            "captcha_0": captcha_hash,
            "captcha_1": guess,
            "action": "finish",
        }
        for key in (
            "name",
            "email",
            "address",
            "city",
            "state",
            "zip",
            "country",
            "phone_number",
            "payment_method",
            "priority",
            "coupon",
        ):
            val = input_value(form, key)
            if val:
                finish_data[key] = val

        if orderer.shipping and not orderer.shipping.is_local_delivery:
            finish_data.update(
                {
                    "name": orderer.shipping.name,
                    "address": orderer.shipping.street,
                    "city": orderer.shipping.city,
                    "state": orderer.shipping.state,
                    "zip": orderer.shipping.zip,
                    "country": orderer.shipping.country or "USA",
                }
            )
        finish_data["email"] = orderer.shipping.email
        pay_label = orderer._resolve_payment_label() or PAYMENT_LABELS.get("bitcoin", "Bitcoin")
        finish_data["payment_method"] = (
            select_value_by_label(select_by_name(form, "payment_method"), pay_label) or "0"
        )
        ship_label = orderer._resolve_shipping_label()
        finish_data["priority"] = (
            select_value_contains(select_by_name(form, "priority"), ship_label)
            if ship_label
            else DEFAULT_SHIPPING_VALUE
        )
        if orderer.discount_code:
            finish_data["coupon"] = orderer.discount_code

        post_url = form_action_url(form, CART_URL)
        resp = await session.post_form(post_url, referer=CART_URL, data=finish_data)
        body = resp.text
        if re.search(r"invalid captcha|incorrect captcha|captcha.*invalid", body, re.I):
            last_error = f"Captcha rejected for '{guess}'"
            refreshed = await session.refresh_captcha()
            if refreshed:
                captcha_hash = refreshed["key"]
            _, cart_html, forms = await session.get_page(CART_URL)
            form = find_form(forms, ORDER_FORM_ID) or form
            continue

        if "btcpay" in str(resp.url).lower() or extract_order_error(body):
            if extract_order_error(body):
                last_error = extract_order_error(body)
                continue
            solve_ms = int((time.time() - started) * 1000)
            orderer._http_finish_response = resp
            return True, f"Captcha solved: {guess}", solver_used, solve_ms, attempt

        if input_value(find_form(parse_forms(body), ORDER_FORM_ID) or {}, "captcha_1") == "":
            solve_ms = int((time.time() - started) * 1000)
            orderer._http_finish_response = resp
            return True, f"Captcha solved: {guess}", solver_used, solve_ms, attempt

        last_error = f"Captcha unclear result for '{guess}'"
        refreshed = await session.refresh_captcha()
        if refreshed:
            captcha_hash = refreshed["key"]
        _, cart_html, forms = await session.get_page(CART_URL)
        form = find_form(forms, ORDER_FORM_ID) or form

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
    try:
        async with IdGodHttpSession(proxy=proxy, timeout=orderer.timeout_ms / 1000) as session:
            if orderer.ui:
                orderer.ui.phase("HTTP")
                orderer.ui.ok("Session ready (no browser)")

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
                )
                results.append(result)
                if not result.success:
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

            if orderer.checkout:
                checkout_started = time.time()
                fill_meta, finish_resp = await _checkout_http(session, orderer)
                timings["checkout_ms"] = int((time.time() - checkout_started) * 1000)
                discount_applied = "coupon" in fill_meta.filled
                discount_msg = (
                    f"Coupon '{orderer.discount_code}' saved with UPDATE"
                    if discount_applied
                    else "Coupon not applied"
                )
                if finish_resp is None and orderer._http_finish_response is not None:
                    finish_resp = orderer._http_finish_response
            else:
                if orderer.discount_code:
                    discount_applied, discount_msg = await _apply_discount_http(session, orderer)
                fill_meta.total_before_discount = total
                fill_meta.total_after_discount = total

            if fill_meta.total_after_discount is None:
                fill_meta.total_after_discount = total
            if fill_meta.total_before_discount is None:
                fill_meta.total_before_discount = total

            savings = None
            if (
                fill_meta.total_before_discount is not None
                and fill_meta.total_after_discount is not None
            ):
                savings = round(fill_meta.total_before_discount - fill_meta.total_after_discount, 2)
                if savings <= 0:
                    savings = None

            payment_url = str(finish_resp.url) if finish_resp else CART_URL
            payment_details = PaymentDetails(invoice_url=payment_url)
            if finish_resp and ("btcpay" in payment_url.lower() or orderer.fetch_payment):
                payment_details = parse_btcpay_html(finish_resp.text, payment_url)
                if payment_details.invoice_url:
                    payment_url = payment_details.invoice_url

            pay_lines = (
                payment_details.summary_lines()
                if payment_details.populated
                else []
            )

            submitted = [r.person.display_name for r in results if r.success]
            price_per = (total / len(submitted)) if total and submitted else None
            elapsed_ms = int((time.time() - run_started) * 1000)
            timings["total_ms"] = elapsed_ms
            if fill_meta.captcha_solve_time_ms:
                timings["captcha_ms"] = fill_meta.captcha_solve_time_ms

            return CheckoutResult(
                success=all(r.success for r in results)
                and (not orderer.checkout_submit or fill_meta.completed),
                message=discount_msg if discount_applied else "Order submitted via HTTP",
                submitted_ids=submitted,
                payment_url=payment_url,
                payment_info="\n".join(pay_lines),
                payment_details=payment_details if payment_details.populated else None,
                total_price=fill_meta.total_after_discount or total,
                total_before_discount=fill_meta.total_before_discount,
                total_after_discount=fill_meta.total_after_discount or total,
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
