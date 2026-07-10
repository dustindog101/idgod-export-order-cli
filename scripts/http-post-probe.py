#!/usr/bin/env python3
"""Explore whether idgod.ph order flow works with raw HTTP POST instead of Playwright.

Read-only / investigative — does not change the production orderer.

Phases:
  analyze  GET /order and /cart, dump forms, cookies, JS requirements
  submit   multipart POST add-to-cart (action=1) via httpx session
  cart     GET /cart after submit and inspect totals / fields
  captcha  GET captcha image URL pattern from cart (if reachable)
  full     analyze → submit → cart

Examples:
  ./scripts/http-post-probe.py --tor --phase analyze
  ./scripts/http-post-probe.py --tor --phase full --fixture tests/fixtures/multi-shipping-live.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from dataclasses import dataclass, field
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from idgod_order_cli.orderer import CART_URL, ORDER_URL, USER_AGENT
from idgod_order_cli.parser import parse_export_file
from idgod_order_cli.proxies import TorManager
from idgod_order_cli.states import (
    expand_state_name,
    map_eye_color,
    map_hair_color,
    map_sex,
    parse_height,
    pick_state_option,
)
from idgod_order_cli.orderer import _prepare_upload_image

ORDER_FORM_ID = "order-form"


class _FormParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.forms: list[dict[str, Any]] = []
        self._stack: list[dict[str, Any]] = []
        self._current_input: dict[str, Any] | None = None
        self.scripts: list[str] = []
        self._in_script = False
        self._script_buf: list[str] = []
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
                {
                    "name": attr.get("name", ""),
                    "id": attr.get("id", ""),
                    "options": [],
                }
            )
        elif tag == "option" and self._stack and self._stack[-1]["selects"]:
            self._stack[-1]["selects"][-1]["options"].append(
                {
                    "value": attr.get("value", ""),
                    "label": "",
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
        elif tag == "script":
            self._in_script = True
            self._script_buf = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "option":
            self._current_option = None
        if tag == "form" and self._stack:
            self.forms.append(self._stack.pop())
        elif tag == "script" and self._in_script:
            self._in_script = False
            body = "".join(self._script_buf)
            if body.strip():
                self.scripts.append(body[:500])
            self._script_buf = []

    def handle_data(self, data: str) -> None:
        if self._in_script:
            self._script_buf.append(data)
            return
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


def parse_forms(html: str) -> _FormParser:
    parser = _FormParser()
    parser.feed(html)
    return parser


def _cookie_summary(jar) -> dict[str, str]:
    out: dict[str, str] = {}
    for c in jar.jar:
        out[c.name] = c.value[:12] + "…" if len(c.value) > 12 else c.value
    return out


def _find_form(forms: list[dict[str, Any]], form_id: str) -> dict[str, Any] | None:
    for form in forms:
        if form.get("id") == form_id:
            return form
    return forms[0] if forms else None


def _select_value_by_label(select: dict[str, Any], label: str) -> str:
    target = label.strip().lower()
    for opt in select.get("options", []):
        if (opt.get("label") or "").strip().lower() == target:
            return opt.get("value", "")
    for opt in select.get("options", []):
        if target in (opt.get("label") or "").strip().lower():
            return opt.get("value", "")
    return ""


def _state_options_from_form(form: dict[str, Any]) -> list[Any]:
    from idgod_order_cli.states import StateOption, estimate_price

    for sel in form.get("selects", []):
        if sel.get("name") == "state" or sel.get("id") == "id_state":
            options = []
            for opt in sel.get("options", []):
                label = (opt.get("label") or "").strip()
                value = opt.get("value", "")
                if label and value:
                    options.append(StateOption(label=label, price=estimate_price(label)))
            return options
    return []


def _tiny_jpeg() -> bytes:
    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", (400, 500), color=(120, 140, 160)).save(buf, "JPEG", quality=90)
    return buf.getvalue()


@dataclass
class ProbeReport:
    phase: str
    ok: bool
    notes: list[str] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"phase": self.phase, "ok": self.ok, "notes": self.notes, "data": self.data}


async def _client(proxy, timeout: float):
    import httpx

    return httpx.AsyncClient(
        proxy=proxy.to_httpx() if proxy else None,
        follow_redirects=True,
        timeout=timeout,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )


def _csrf_headers(client, referer: str) -> dict[str, str]:
    token = client.cookies.get("csrftoken", "")
    headers = {
        "Referer": referer,
        "Origin": "https://www.idgod.ph",
    }
    if token:
        headers["X-CSRFToken"] = token
    return headers


async def phase_analyze(client, *, out_dir: Path | None) -> ProbeReport:
    notes: list[str] = []
    data: dict[str, Any] = {}

    for label, url in (("order", ORDER_URL), ("cart", CART_URL)):
        resp = await client.get(url)
        html = resp.text
        parsed = parse_forms(html)
        form = _find_form(parsed.forms, ORDER_FORM_ID if label == "order" else "")
        data[label] = {
            "url": str(resp.url),
            "status": resp.status_code,
            "bytes": len(resp.content),
            "title": _extract_title(html),
            "forms": parsed.forms,
            "script_count": len(parsed.scripts),
            "has_jquery_validator": any("validator" in s for s in parsed.scripts),
            "has_recaptcha": "recaptcha" in html.lower(),
            "has_captcha_image": bool(re.search(r"/captcha/image/", html)),
            "csrf_present": "csrfmiddlewaretoken" in html,
            "session_cookie": _cookie_summary(client.cookies),
        }
        if out_dir:
            (out_dir / f"{label}.html").write_text(html, encoding="utf-8")

        if label == "order" and form:
            required = [
                i["name"]
                for i in form.get("inputs", [])
                if i.get("required") and i.get("name")
            ]
            file_inputs = [i["name"] for i in form.get("inputs", []) if i.get("type") == "file"]
            data[label]["required_input_names"] = required
            data[label]["file_input_names"] = file_inputs
            notes.append(f"/order form action={form.get('action')!r} enctype={form.get('enctype')!r}")
            notes.append(f"/order file inputs: {file_inputs or 'none'}")
        if label == "cart":
            empty = bool(re.search(r"cart contents\s*\(0\)|your cart is empty|start order now", html, re.I))
            data[label]["appears_empty"] = empty
            notes.append(f"/cart appears empty: {empty}")

    ok = data.get("order", {}).get("status") == 200 and data.get("order", {}).get("csrf_present")
    return ProbeReport("analyze", ok, notes, data)


async def _download_photo(client, url: str, fallback_path: Path | None) -> tuple[bytes, str, str]:
    if url:
        try:
            resp = await client.get(url)
            if resp.status_code < 400 and resp.content:
                ctype = resp.headers.get("content-type", "image/jpeg").split(";")[0]
                ext = ".webp" if "webp" in ctype else ".jpg"
                path = Path("/tmp/http-probe-photo" + ext)
                path.write_bytes(resp.content)
                prepared = _prepare_upload_image(path)
                return prepared.read_bytes(), prepared.name, "image/jpeg"
        except Exception:
            pass
    if fallback_path and fallback_path.exists():
        prepared = _prepare_upload_image(fallback_path)
        return prepared.read_bytes(), prepared.name, "image/jpeg"
    return _tiny_jpeg(), "probe-photo.jpg", "image/jpeg"


async def phase_submit(
    client,
    *,
    person,
    photo_bytes: bytes,
    photo_name: str,
    photo_type: str,
    out_dir: Path | None,
) -> ProbeReport:
    notes: list[str] = []
    get_resp = await client.get(ORDER_URL)
    html = get_resp.text
    parsed = parse_forms(html)
    form = _find_form(parsed.forms, ORDER_FORM_ID)
    if not form:
        return ProbeReport("submit", False, ["order-form not found"], {"status": get_resp.status_code})

    csrf = ""
    for inp in form.get("inputs", []):
        if inp.get("name") == "csrfmiddlewaretoken":
            csrf = inp.get("value", "")
            break
    if not csrf:
        m = re.search(r'name="csrfmiddlewaretoken"\s+value="([^"]+)"', html)
        csrf = m.group(1) if m else ""
    if not csrf:
        return ProbeReport("submit", False, ["csrf token missing"], {})

    state_options = _state_options_from_form(form)
    chosen, note = pick_state_option(expand_state_name(person.state), state_options, cheapest=True)
    if chosen is None:
        return ProbeReport("submit", False, [note or "state not found"], {"state_options": len(state_options)})

    feet, inches = parse_height(person.height or "5'6\"")
    selects = {s.get("name"): s for s in form.get("selects", []) if s.get("name")}
    eyes_val = _select_value_by_label(selects.get("eyes", {}), map_eye_color(person.eye_color or "Brown"))
    hair_val = _select_value_by_label(selects.get("hair", {}), map_hair_color(person.hair_color or "Brown"))
    gender_val = _select_value_by_label(selects.get("gender", {}), map_sex(person.sex or "Female"))

    fields: dict[str, Any] = {
        "csrfmiddlewaretoken": csrf,
        "first_name": person.first_name,
        "middle_name": person.middle_name or "",
        "last_name": person.last_name,
        "date_of_birth": person.dob,
        "state": "",
        "height_feet": feet,
        "height_inches": inches,
        "weight": person.weight or "130",
        "eyes": eyes_val,
        "hair": hair_val,
        "gender": gender_val,
        "address1": person.street or "123 Main St",
        "address2": "",
        "city": person.city,
        "zip": person.zip,
        "action": "1",
    }
    if not fields["state"]:
        for sel in form.get("selects", []):
            if sel.get("name") == "state":
                for opt in sel.get("options", []):
                    if chosen.label.lower() in (opt.get("label") or "").lower():
                        fields["state"] = opt.get("value", "")
                        break

    files = {
        "picture": (photo_name, photo_bytes, photo_type),
    }

    action_url = urljoin(ORDER_URL, form.get("action") or ORDER_URL)
    started = time.time()
    post_resp = await client.post(
        action_url,
        data=fields,
        files=files,
        headers=_csrf_headers(client, ORDER_URL),
    )
    elapsed_ms = int((time.time() - started) * 1000)
    body = post_resp.text
    if out_dir:
        (out_dir / "submit-response.html").write_text(body, encoding="utf-8")

    error = _extract_error(body)
    redirected_to_cart = CART_URL in str(post_resp.url)
    still_on_order = ORDER_URL in str(post_resp.url)
    cart_hint = bool(re.search(r"cart|added|checkout", body, re.I))

    notes.append(f"POST {action_url} → {post_resp.status_code} in {elapsed_ms}ms")
    notes.append(f"final URL: {post_resp.url}")
    if error:
        notes.append(f"error hint: {error}")

    ok = post_resp.status_code < 400 and not error and (redirected_to_cart or cart_hint or not still_on_order)
    return ProbeReport(
        "submit",
        ok,
        notes,
        {
            "status": post_resp.status_code,
            "elapsed_ms": elapsed_ms,
            "final_url": str(post_resp.url),
            "redirected_to_cart": redirected_to_cart,
            "still_on_order": still_on_order,
            "error_hint": error,
            "state_selected": chosen.label,
            "posted_fields": sorted(fields.keys()),
            "cookies_after": _cookie_summary(client.cookies),
        },
    )


async def phase_cart(client, *, out_dir: Path | None) -> ProbeReport:
    resp = await client.get(CART_URL)
    html = resp.text
    if out_dir:
        (out_dir / "cart-after-submit.html").write_text(html, encoding="utf-8")

    parsed = parse_forms(html)
    empty = bool(re.search(r"cart contents\s*\(0\)|your cart is empty|start order now", html, re.I))
    total_m = re.search(r'id="total"[^>]*>([^<]+)<', html)
    total = total_m.group(1).strip() if total_m else ""
    email_present = any(i.get("id") == "id_email" for f in parsed.forms for i in f.get("inputs", []))
    captcha_present = any(i.get("id") == "id_captcha_1" for f in parsed.forms for i in f.get("inputs", []))

    notes = [
        f"GET /cart status={resp.status_code}",
        f"empty={empty} total={total!r} email_field={email_present} captcha={captcha_present}",
    ]
    ok = not empty and bool(total)
    return ProbeReport(
        "cart",
        ok,
        notes,
        {
            "status": resp.status_code,
            "appears_empty": empty,
            "total": total,
            "checkout_fields_present": email_present,
            "captcha_present": captcha_present,
            "forms": parsed.forms,
        },
    )


async def phase_captcha(client) -> ProbeReport:
    resp = await client.get(CART_URL)
    html = resp.text
    m = re.search(r'(/captcha/image/[^"\']+)', html)
    if not m:
        return ProbeReport("captcha", False, ["no captcha image URL on /cart"], {})
    img_url = urljoin(CART_URL, m.group(1))
    img_resp = await client.get(img_url)
    notes = [f"captcha GET {img_url} → {img_resp.status_code}, {len(img_resp.content)} bytes"]
    hash_m = re.search(r'name="captcha_0"\s+value="([^"]+)"', html)
    return ProbeReport(
        "captcha",
        img_resp.status_code < 400 and len(img_resp.content) > 100,
        notes,
        {
            "image_url": img_url,
            "image_bytes": len(img_resp.content),
            "captcha_hash": hash_m.group(1) if hash_m else "",
            "content_type": img_resp.headers.get("content-type", ""),
        },
    )


def _extract_title(html: str) -> str:
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else ""


def _extract_error(body: str) -> str:
    for pat in (
        r"couldn't add that card[^<]*",
        r"please check the highlighted fields[^<]*",
        r"new photo is required[^<]*",
        r"class=\"[^\"]*error[^\"]*\"[^>]*>([^<]+)",
    ):
        m = re.search(pat, body, re.I)
        if m:
            return re.sub(r"\s+", " ", m.group(0)).strip()[:200]
    return ""


async def run_probe(args: argparse.Namespace) -> dict[str, Any]:
    tor_mgr = TorManager()
    proxy = None
    try:
        if args.tor:
            proxy = tor_mgr.start(timeout=args.timeout)
        elif args.proxy:
            from idgod_order_cli.proxies import parse_proxy_line

            proxy = parse_proxy_line(args.proxy)

        out_dir = Path(args.out_dir).expanduser() if args.out_dir else None
        if out_dir:
            out_dir.mkdir(parents=True, exist_ok=True)

        person = None
        if args.fixture:
            bundle = parse_export_file(Path(args.fixture))
            person = bundle.people[0]

        phases = [args.phase] if args.phase != "full" else ["analyze", "submit", "cart", "captcha"]
        reports: list[ProbeReport] = []

        async with await _client(proxy, args.timeout) as client:
            photo_bytes, photo_name, photo_type = _tiny_jpeg(), "probe-photo.jpg", "image/jpeg"
            if person and (person.photo or args.fallback_photo):
                photo_bytes, photo_name, photo_type = await _download_photo(
                    client,
                    person.photo,
                    Path(args.fallback_photo).expanduser() if args.fallback_photo else None,
                )

            for phase in phases:
                if phase == "analyze":
                    reports.append(await phase_analyze(client, out_dir=out_dir))
                elif phase == "submit":
                    if not person:
                        reports.append(ProbeReport("submit", False, ["--fixture required for submit"]))
                        continue
                    reports.append(
                        await phase_submit(
                            client,
                            person=person,
                            photo_bytes=photo_bytes,
                            photo_name=photo_name,
                            photo_type=photo_type,
                            out_dir=out_dir,
                        )
                    )
                elif phase == "cart":
                    reports.append(await phase_cart(client, out_dir=out_dir))
                elif phase == "captcha":
                    reports.append(await phase_captcha(client))
                else:
                    reports.append(ProbeReport(phase, False, [f"unknown phase {phase!r}"]))

        return {
            "proxy": proxy.display if proxy else "direct",
            "phases": [r.to_dict() for r in reports],
            "verdict": _verdict(reports),
            "out_dir": str(out_dir) if out_dir else "",
        }
    finally:
        tor_mgr.stop()


def _verdict(reports: list[ProbeReport]) -> dict[str, Any]:
    by_name = {r.phase: r for r in reports}
    analyze = by_name.get("analyze")
    submit = by_name.get("submit")
    cart = by_name.get("cart")

    can_replace_browser = False
    blockers: list[str] = []
    partial: list[str] = []

    if not analyze or not analyze.ok:
        blockers.append("Cannot reach /order with CSRF over HTTP")
    else:
        partial.append("GET /order + CSRF session works over httpx")

    order_data = (analyze.data.get("order", {}) if analyze else {})
    if order_data.get("has_jquery_validator"):
        partial.append("Bootstrap/jQuery validator present — may need field ordering or extra POST fields")
    if order_data.get("file_input_names"):
        partial.append("Multipart file upload required for picture (and maybe signature)")

    if submit:
        if submit.ok:
            partial.append("POST add-to-cart returned success signals")
        else:
            blockers.append(f"POST add-to-cart failed: {submit.data.get('error_hint') or submit.notes}")

    if cart:
        if cart.ok:
            partial.append("Cart has items after HTTP POST — add-to-cart likely works without browser")
        elif submit and submit.ok:
            blockers.append("POST looked OK but cart still empty — session or hidden field mismatch")
        else:
            blockers.append("Cart empty — browser session may be required for add-to-cart")

    partial.append("Checkout FINISH ORDER still needs captcha solve (HTTP feasible if captcha OCR works)")
    partial.append("Photo validation may reject synthetic/test images — use real export photo URLs")

    if analyze and analyze.ok and submit and submit.ok and cart and cart.ok:
        can_replace_browser = True

    return {
        "http_viable_for_add_to_cart": can_replace_browser,
        "http_viable_for_full_checkout": False,
        "blockers": blockers,
        "partial_wins": partial,
        "recommendation": (
            "Hybrid: httpx for add-to-cart + captcha fetch; keep Playwright only if POST cart fails"
            if not can_replace_browser
            else "POC passed: try httpx orderer for add-to-cart; Playwright still needed for captcha unless OCR path is solid"
        ),
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Probe raw HTTP POST vs Playwright for idgod.ph")
    p.add_argument("--tor", action="store_true")
    p.add_argument("--proxy", help="host:port or host:port:user:pass")
    p.add_argument("--phase", default="analyze", choices=["analyze", "submit", "cart", "captcha", "full"])
    p.add_argument("--fixture", help="Export JSON/XLSX for submit phase")
    p.add_argument("--fallback-photo", help="Local photo if export URL dead")
    p.add_argument("--timeout", type=float, default=60.0)
    p.add_argument("--out-dir", default="/tmp/idgod-http-probe", help="Save HTML dumps here")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    result = asyncio.run(run_probe(args))
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Proxy: {result['proxy']}")
        print()
        for phase in result["phases"]:
            mark = "OK" if phase["ok"] else "FAIL"
            print(f"[{mark}] {phase['phase']}")
            for note in phase.get("notes", []):
                print(f"  - {note}")
            print()
        v = result["verdict"]
        print("Verdict:")
        print(f"  add-to-cart via HTTP: {'yes' if v['http_viable_for_add_to_cart'] else 'no / unproven'}")
        print(f"  full checkout via HTTP: {v['http_viable_for_full_checkout']}")
        for item in v.get("blockers", []):
            print(f"  blocker: {item}")
        for item in v.get("partial_wins", []):
            print(f"  note: {item}")
        print(f"  → {v['recommendation']}")
        if result.get("out_dir"):
            print(f"\nHTML dumps: {result['out_dir']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
