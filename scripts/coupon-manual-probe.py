#!/usr/bin/env python3
"""Headed cart probe: add 1 ID, apply coupon, inspect cart + optional checkout invoice."""

from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from idgod_order_cli.http_forms import (
    finalize_coupon_result,
    parse_fiat_amount,
    read_cart_total,
)
from idgod_order_cli.models import ShippingInfo
from idgod_order_cli.orderer import IdGodOrderer, USER_AGENT, CART_URL
from idgod_order_cli.parser import parse_export_file
from idgod_order_cli.selectors import CART_BUTTONS, CART_SELECTORS


async def main() -> int:
    export = Path(
        sys.argv[1] if len(sys.argv) > 1 else "/Users/king/Downloads/orders-2026-07-10.json"
    )
    headed = "--headed" in sys.argv
    do_checkout = "--checkout" in sys.argv
    code = "hartlr"
    for i, a in enumerate(sys.argv):
        if a == "--discount" and i + 1 < len(sys.argv):
            code = sys.argv[i + 1]

    people = parse_export_file(export).people[:1]
    person = people[0]
    shipping = ShippingInfo(
        name="Anaya Samsotha-Cooley",
        street="5125 Leona St",
        city="Oakland",
        state="CA",
        zip="94619",
        country="USA",
        email="test@proton.me",
        phone="5105550199",
    )

    orderer = IdGodOrderer(
        use_tor=True,
        discount_code=code,
        fallback_photo="/Users/king/Desktop/good.jpg",
        fallback_signature="/Users/king/Desktop/good.jpg",
        shipping=shipping,
        checkout=do_checkout,
        checkout_submit=do_checkout,
        headless=not headed,
        transport="browser",
        fetch_payment=True,
        require_coupon=False,
    )

    from playwright.async_api import async_playwright

    proxy = await orderer._resolve_proxy()
    out: dict = {"coupon": code, "headed": headed, "checkout": do_checkout, "proxy": proxy.display if proxy else ""}

    async with async_playwright() as pw:
        browser = await orderer._launch_browser(pw)
        ctx = await browser.new_context(user_agent=USER_AGENT, viewport={"width": 1400, "height": 900})
        page = await ctx.new_page()
        page.set_default_timeout(120000)

        r = await orderer._fill_person(page, person, checkout=True)
        out["add_person"] = {"success": r.success, "message": r.message}
        if not r.success:
            print(json.dumps(out, indent=2))
            await browser.close()
            orderer._tor_mgr.stop()
            return 1

        if CART_URL not in page.url:
            await page.goto(CART_URL, wait_until="domcontentloaded")
            await page.wait_for_timeout(1500)

        cart_before, _ = await orderer._read_totals(page)
        out["cart_total_before_coupon"] = cart_before

        # Fill checkout fields + coupon like CLI
        fill = await orderer._fill_checkout(page)
        out["checkout_fill"] = {
            "completed": fill.completed,
            "filled": fill.filled,
            "message": fill.message,
            "total_before": fill.total_before_discount,
            "total_after": fill.total_after_discount,
        }

        cart_after, _ = await orderer._read_totals(page)
        out["cart_total_after_update"] = cart_after

        coupon_val = ""
        if await page.locator(CART_SELECTORS["coupon"]).count():
            coupon_val = await page.locator(CART_SELECTORS["coupon"]).input_value()
        out["coupon_field_value"] = coupon_val

        body = await page.content()
        line_prices = re.findall(
            r"<td[^>]*>.*?\$\s*([\d,]+(?:\.\d{2})?)",
            body,
            re.I | re.S,
        )
        out["dollar_amounts_in_html"] = line_prices[:20]

        if do_checkout:
            if headed:
                print("\n>>> HEADED: solve captcha in browser if needed, then press Enter here <<<", flush=True)
                await asyncio.get_event_loop().run_in_executor(None, input)
            result = await orderer.submit(people)
            out["submit"] = {
                "success": result.success,
                "message": result.message,
                "discount_applied": result.discount_applied,
                "cart": result.total_before_discount,
                "invoice": (result.payment_details or {}).total_fiat if result.payment_details else None,
                "payment_url": result.payment_url,
            }
            if result.payment_details and result.payment_details.total_fiat:
                applied, msg, savings, inv = finalize_coupon_result(
                    code, result.total_before_discount, result.payment_details.total_fiat
                )
                out["invoice_check"] = {
                    "applied": applied,
                    "message": msg,
                    "savings": savings,
                    "invoice_total": inv,
                }

        dump = Path("/tmp/coupon-manual-probe.json")
        dump.write_text(json.dumps(out, indent=2), encoding="utf-8")
        if headed:
            await page.wait_for_timeout(3000)
        await browser.close()

    orderer._tor_mgr.stop()
    print(json.dumps(out, indent=2))
    print(f"\nSaved → {dump}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
