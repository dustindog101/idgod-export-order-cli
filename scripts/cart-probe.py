#!/usr/bin/env python3
"""Probe cart state after order form submit over Tor."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from idgod_order_cli.orderer import ORDER_URL, USER_AGENT, IdGodOrderer, CART_URL
from idgod_order_cli.parser import parse_export_file
from idgod_order_cli.selectors import CART_SELECTORS, SELECTORS


async def main() -> int:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "tests/fixtures/multi-shipping-live.json")
    people = parse_export_file(path).people[:1]
    person = people[0]

    orderer = IdGodOrderer(use_tor=True, headless=True, timeout_ms=120000)
    proxy = await orderer._resolve_proxy()
    print("proxy:", proxy.display if proxy else "none")

    from playwright.async_api import async_playwright

    async with async_playwright() as pw:
        browser = await orderer._launch_browser(pw)
        context = await browser.new_context(user_agent=USER_AGENT, viewport={"width": 1400, "height": 900})
        page = await context.new_page()
        page.set_default_timeout(orderer.timeout_ms)

        await page.goto(ORDER_URL, wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)
        result = await orderer._fill_person(page, person, checkout=True)
        print("fill result:", result.success, result.message)
        print("url after submit:", page.url)

        await page.wait_for_timeout(3000)
        print("url after wait:", page.url)

        checks = {}
        for key, sel in {**SELECTORS, **CART_SELECTORS}.items():
            if key in ("captcha_image", "captcha_hash"):
                continue
            checks[key] = await page.locator(sel).count()

        total = await page.locator("#total").count()
        total_text = ""
        if total:
            total_text = await page.locator("#total").first.inner_text()

        body_snip = (await page.inner_text("body"))[:800]
        out = {
            "url": page.url,
            "total": total_text,
            "selectors": checks,
            "body": body_snip,
        }
        dump = Path("/tmp/cart-probe.json")
        dump.write_text(json.dumps(out, indent=2), encoding="utf-8")
        print(json.dumps(out, indent=2))

        if CART_URL not in page.url:
            print("navigating to cart...")
            await page.goto(CART_URL, wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)
            total2 = await page.locator("#total").first.inner_text() if await page.locator("#total").count() else ""
            email_count = await page.locator(CART_SELECTORS["email"]).count()
            print("after goto cart url:", page.url, "total:", total2, "email fields:", email_count)

        await browser.close()
    orderer._tor_mgr.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
