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
                {"value": attr.get("value", ""), "label": ""}
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


def captcha_image_url(html: str, page_url: str) -> str:
    m = re.search(r'(/captcha/image/[^"\']+)', html)
    return urljoin(page_url, m.group(1)) if m else ""


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
