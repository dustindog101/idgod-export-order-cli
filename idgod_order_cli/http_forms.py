"""Parse idgod.ph HTML forms for HTTP transport."""

from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin

ORDER_FORM_ID = "order-form"
BASE_URL = "https://www.idgod.ph"


class FormParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.forms: list[dict[str, Any]] = []
        self._stack: list[dict[str, Any]] = []
        self._current_option: int | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {k: (v or "") for k, v in attrs}
        if tag == "form":
            self._stack.append(
                {
                    "id": attr.get("id", ""),
                    "action": attr.get("action", ""),
                    "method": (attr.get("method", "get") or "get").lower(),
                    "enctype": attr.get("enctype", ""),
                    "inputs": [],
                    "selects": [],
                    "buttons": [],
                }
            )
        elif tag == "input" and self._stack:
            self._stack[-1]["inputs"].append(
                {
                    "type": attr.get("type", "text"),
                    "name": attr.get("name", ""),
                    "id": attr.get("id", ""),
                    "value": attr.get("value", ""),
                    "required": "required" in attr,
                }
            )
        elif tag == "select" and self._stack:
            self._stack[-1]["selects"].append(
                {"name": attr.get("name", ""), "id": attr.get("id", ""), "options": []}
            )
        elif tag == "option" and self._stack and self._stack[-1]["selects"]:
            self._stack[-1]["selects"][-1]["options"].append(
                {
                    "value": attr.get("value", ""),
                    "label": "",
                    "selected": "selected" in attr,
                }
            )
            self._current_option = len(self._stack[-1]["selects"][-1]["options"]) - 1
        elif tag == "button" and self._stack:
            self._stack[-1]["buttons"].append(
                {
                    "type": attr.get("type", "submit"),
                    "name": attr.get("name", ""),
                    "value": attr.get("value", ""),
                    "id": attr.get("id", ""),
                    "text": "",
                }
            )

    def handle_endtag(self, tag: str) -> None:
        if tag == "option":
            self._current_option = None
        if tag == "form" and self._stack:
            self.forms.append(self._stack.pop())

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if not text:
            return
        if self._stack and self._stack[-1]["buttons"]:
            self._stack[-1]["buttons"][-1]["text"] += text
        if (
            self._current_option is not None
            and self._stack
            and self._stack[-1]["selects"]
            and self._stack[-1]["selects"][-1]["options"]
        ):
            opt = self._stack[-1]["selects"][-1]["options"][self._current_option]
            opt["label"] = (opt.get("label", "") + " " + text).strip()


def parse_forms(html: str) -> list[dict[str, Any]]:
    parser = FormParser()
    parser.feed(html)
    return parser.forms


def find_form(forms: list[dict[str, Any]], form_id: str = "") -> dict[str, Any] | None:
    if form_id:
        for form in forms:
            if form.get("id") == form_id:
                return form
    for form in forms:
        if form.get("id") == ORDER_FORM_ID:
            return form
    return forms[0] if forms else None


def extract_csrf(html: str, form: dict[str, Any] | None = None) -> str:
    if form:
        for inp in form.get("inputs", []):
            if inp.get("name") == "csrfmiddlewaretoken" and inp.get("value"):
                return inp["value"]
    m = re.search(r'name="csrfmiddlewaretoken"\s+value="([^"]+)"', html)
    return m.group(1) if m else ""


def input_value(form: dict[str, Any], name: str) -> str:
    for inp in form.get("inputs", []):
        if inp.get("name") == name:
            return str(inp.get("value") or "")
    return ""


def select_by_name(form: dict[str, Any], name: str) -> dict[str, Any] | None:
    for sel in form.get("selects", []):
        if sel.get("name") == name:
            return sel
    return None


def select_value_by_label(select: dict[str, Any] | None, label: str) -> str:
    if not select:
        return ""
    target = label.strip().lower()
    for opt in select.get("options", []):
        if (opt.get("label") or "").strip().lower() == target:
            return opt.get("value", "")
    for opt in select.get("options", []):
        if target in (opt.get("label") or "").strip().lower():
            return opt.get("value", "")
    return ""


def select_value_contains(select: dict[str, Any] | None, needle: str) -> str:
    if not select:
        return ""
    needle_l = needle.strip().lower()
    for opt in select.get("options", []):
        if needle_l in (opt.get("label") or "").strip().lower():
            return opt.get("value", "")
    return ""


def form_action_url(form: dict[str, Any], page_url: str) -> str:
    return urljoin(page_url, form.get("action") or page_url)


def read_cart_total(html: str) -> tuple[float | None, int, bool]:
    total_m = re.search(r'id="total"[^>]*>([^<]+)<', html)
    total_text = total_m.group(1).strip() if total_m else ""
    m = re.search(r"\$?\s*([\d,]+\.?\d*)", total_text.replace(",", "")) if total_text else None
    total = float(m.group(1)) if m else None
    empty = bool(re.search(r"cart contents\s*\(0\)|your cart is empty|start order now", html, re.I))
    cart_match = re.search(r"cart contents\s*\((\d+)\)", html, re.I)
    count = int(cart_match.group(1)) if cart_match else (0 if empty else 1)
    if not empty and total and count == 0:
        count = 1
    return total, count, empty


def _selected_option_value(select: dict[str, Any]) -> str:
    options = select.get("options", [])
    for opt in options:
        if opt.get("selected") and opt.get("value") is not None:
            return str(opt.get("value", ""))
    for opt in options:
        if opt.get("value"):
            return str(opt.get("value", ""))
    return ""


def scrape_form_fields(html: str, form_id: str = ORDER_FORM_ID) -> dict[str, str]:
    """Extract input/select values from a form block in cart/order HTML."""
    m = re.search(
        rf'<form[^>]*\bid=["\']{re.escape(form_id)}["\'][^>]*>(.*?)</form>',
        html,
        re.I | re.S,
    )
    chunk = m.group(1) if m else html
    fields: dict[str, str] = {}

    for tag_m in re.finditer(r"<(input|select|textarea)([^>]*)>", chunk, re.I):
        tag_name = tag_m.group(1).lower()
        attrs = tag_m.group(2)
        name_m = re.search(r'\bname=["\']([^"\']+)["\']', attrs, re.I)
        if not name_m:
            continue
        name = name_m.group(1)
        if tag_name == "input":
            type_m = re.search(r'\btype=["\']([^"\']+)["\']', attrs, re.I)
            input_type = (type_m.group(1) if type_m else "text").lower()
            if input_type in ("submit", "button", "image", "file"):
                continue
            val_m = re.search(r'\bvalue=["\']([^"\']*)["\']', attrs, re.I)
            fields[name] = val_m.group(1) if val_m else ""
        elif tag_name == "textarea":
            close = re.search(
                rf"<textarea[^>]*\bname=[\"']{re.escape(name)}[\"'][^>]*>(.*?)</textarea>",
                chunk,
                re.I | re.S,
            )
            fields[name] = (close.group(1) if close else "").strip()
        elif tag_name == "select":
            sel_m = re.search(
                rf"<select[^>]*\bname=[\"']{re.escape(name)}[\"'][^>]*>(.*?)</select>",
                chunk,
                re.I | re.S,
            )
            if not sel_m:
                continue
            body = sel_m.group(1)
            selected = re.search(
                r"<option[^>]*\bselected\b[^>]*\bvalue=[\"']([^\"']*)[\"']",
                body,
                re.I,
            )
            if selected:
                fields[name] = selected.group(1)
                continue
            first = re.search(r'<option[^>]*\bvalue=["\']([^"\']*)["\']', body, re.I)
            fields[name] = first.group(1) if first else ""

    return fields


def form_post_data(form: dict[str, Any], html: str = "") -> dict[str, str]:
    """Merge parsed form defaults with regex-scraped values (includes hidden cart fields)."""
    data: dict[str, str] = {}
    if html:
        data.update(scrape_form_fields(html, form.get("id") or ORDER_FORM_ID))
    for inp in form.get("inputs", []):
        name = inp.get("name")
        if not name:
            continue
        input_type = (inp.get("type") or "text").lower()
        if input_type in ("submit", "button", "image", "file"):
            continue
        data[name] = str(inp.get("value") or "")
    for sel in form.get("selects", []):
        name = sel.get("name")
        if not name:
            continue
        data[name] = _selected_option_value(sel)
    return data


def detect_coupon_rejection(html: str, code: str = "") -> str | None:
    for pat in (
        r"coupon[^<]{0,40}(?:invalid|expired|not found|does not exist|incorrect)",
        r"(?:invalid|expired|not found|does not exist)[^<]{0,40}coupon",
        r"discount code[^<]{0,40}(?:invalid|expired|not found)",
    ):
        m = re.search(pat, html, re.I)
        if m:
            return re.sub(r"\s+", " ", m.group(0)).strip()[:160]
    if code:
        for pat in (
            rf"{re.escape(code)}[^<]{{0,40}}(?:invalid|expired|not found)",
            rf"(?:invalid|expired|not found)[^<]{{0,40}}{re.escape(code)}",
        ):
            m = re.search(pat, html, re.I)
            if m:
                return re.sub(r"\s+", " ", m.group(0)).strip()[:160]
    return None


def parse_fiat_amount(text: str) -> float | None:
    if not text:
        return None
    m = re.search(r"\$?\s*([\d,]+\.?\d*)", text.replace(",", ""))
    return float(m.group(1)) if m else None


def invoice_reflects_discount(cart_total: float | None, invoice_fiat: str) -> bool:
    """True when BTCPay fiat is well below undiscounted cart (coupon applied at checkout).

    idgod.ph often keeps #total unchanged after UPDATE; the discount shows on the invoice.
    Historical runs: 1 ID cart $130 → invoice $85; 4 IDs cart $480 → invoice $260.
    """
    cart = cart_total or 0.0
    fiat = parse_fiat_amount(invoice_fiat)
    if not cart or not fiat:
        return False
    # Discounted invoices are ~55–65% of cart; full price is cart + ~$20 shipping.
    return fiat < cart * 0.75


def coupon_savings_message(
    code: str,
    before: float | None,
    after: float | None,
    *,
    invoice_fiat: str = "",
) -> tuple[bool, str, float | None]:
    fiat = parse_fiat_amount(invoice_fiat)
    if code and before is not None and fiat is not None and invoice_reflects_discount(before, invoice_fiat):
        savings = round(before - fiat, 2)
        if savings > 0:
            return True, (
                f"Coupon '{code}' applied — invoice ${fiat:.2f} "
                f"(cart showed ${before:.2f})"
            ), savings
    if code and before is not None and fiat is not None and not invoice_reflects_discount(before, invoice_fiat):
        return False, (
            f"Coupon '{code}' not on invoice (${fiat:.2f} for cart ${before:.2f})"
        ), None
    if not code or before is None or after is None:
        return False, "", None
    savings = round(before - after, 2)
    if savings > 0:
        return True, (
            f"Coupon '{code}' applied — saved ${savings:.2f} "
            f"(${before:.2f} → ${after:.2f})"
        ), savings
    pending = (
        f"Coupon '{code}' entered (cart still ${before:.2f}; "
        "idgod often applies discount on the BTCPay invoice only)"
    )
    return False, pending, None


def finalize_coupon_result(
    code: str,
    cart_total: float | None,
    invoice_fiat: str,
) -> tuple[bool, str, float | None, float | None]:
    """Resolve coupon from BTCPay invoice (authoritative) vs cart #total (often unchanged)."""
    applied, msg, savings = coupon_savings_message(
        code, cart_total, cart_total, invoice_fiat=invoice_fiat
    )
    return applied, msg, savings, parse_fiat_amount(invoice_fiat)


def captcha_image_url(html: str, page_url: str) -> str:
    m = re.search(r'(/captcha/image/[^"\']+)', html)
    return urljoin(page_url, m.group(1)) if m else ""


def captcha_hash_from_image_url(img_url: str) -> str:
    """django-simple-captcha key embedded in /captcha/image/<key>/ URLs."""
    m = re.search(r"/captcha/image/([^/]+)/", img_url or "")
    return m.group(1) if m else ""


def extract_order_error(body: str) -> str:
    for pat in (
        r"couldn't add that card[^<]*",
        r"please check the highlighted fields[^<]*",
        r"new photo is required[^<]*",
        r"invalid captcha[^<]*",
        r"incorrect captcha[^<]*",
    ):
        m = re.search(pat, body, re.I)
        if m:
            return re.sub(r"\s+", " ", m.group(0)).strip()[:200]
    return ""
