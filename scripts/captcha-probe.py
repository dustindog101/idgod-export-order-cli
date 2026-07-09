#!/usr/bin/env python3
"""Fetch idgod cart captchas over Tor/proxy and compare OCR + image sources."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from idgod_order_cli.captcha import (  # noqa: E402
    best_captcha_guess,
    normalize_captcha_text,
    solve_captcha_image,
)
from idgod_order_cli.orderer import ORDER_URL  # noqa: E402
from idgod_order_cli.proxies import TorManager, load_proxies_from_file, parse_proxy_line  # noqa: E402


async def _fetch_via_page_eval(page) -> bytes | None:
    data = await page.evaluate(
        """async () => {
          const img = document.querySelector('img.captcha, img[src*="/captcha/image/"]');
          if (!img || !img.src) return null;
          const r = await fetch(img.src, {credentials: 'same-origin'});
          if (!r.ok) return null;
          const buf = await r.arrayBuffer();
          return Array.from(new Uint8Array(buf));
        }"""
    )
    return bytes(data) if data else None


async def _fetch_via_request(page, src: str) -> bytes | None:
    from urllib.parse import urljoin

    full_url = urljoin(page.url, src)
    resp = await page.request.get(full_url)
    if resp.ok:
        body = await resp.body()
        if body and body[:8] == b"\x89PNG\r\n\x1a\n":
            return body
    return None


async def _fetch_via_screenshot(page) -> bytes | None:
    img = page.locator('img.captcha, img[src*="/captcha/image/"]').first
    if await img.count() == 0:
        return None
    shot = await img.screenshot()
    if shot and shot[:8] == b"\x89PNG\r\n\x1a\n":
        return shot
    return None


async def probe(proxy, *, samples: int, out_dir: Path, headed: bool) -> dict:
    from playwright.async_api import async_playwright

    out_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []

    async with async_playwright() as pw:
        launch_kwargs: dict = {
            "headless": not headed,
            "args": ["--no-sandbox", "--disable-dev-shm-usage"],
        }
        if proxy:
            launch_kwargs["proxy"] = proxy.to_playwright()
        try:
            browser = await pw.chromium.launch(**launch_kwargs)
        except Exception:
            browser = await pw.chromium.launch(channel="chrome", **launch_kwargs)

        page = await browser.new_page()
        page.set_default_timeout(60000)
        await page.goto(ORDER_URL, wait_until="domcontentloaded")
        await page.goto("https://www.idgod.ph/cart", wait_until="domcontentloaded")
        await page.wait_for_timeout(1500)

        has_captcha = await page.locator('img.captcha, img[src*="/captcha/image/"]').count()
        if not has_captcha:
            raise RuntimeError(
                "No captcha on /cart (cart is empty). Add at least one ID first, e.g.\n"
                "  ./idgod-order order orders.xlsx --tor --limit 1 --checkout ...\n"
                "Then inspect ~/.cache/idgod-order-cli/captcha-debug/ from that run."
            )

        for i in range(1, samples + 1):
            src = await page.locator('img.captcha, img[src*="/captcha/image/"]').first.get_attribute("src")
            captcha_hash = await page.locator("#id_captcha_0").input_value() if await page.locator("#id_captcha_0").count() else ""

            methods: dict[str, dict] = {}
            for name, fetcher in (
                ("page_fetch", lambda: _fetch_via_page_eval(page)),
                ("playwright_request", lambda: _fetch_via_request(page, src or "")),
                ("element_screenshot", lambda: _fetch_via_screenshot(page)),
            ):
                started = time.time()
                try:
                    body = await fetcher()
                    ok = bool(body and body[:8] == b"\x89PNG\r\n\x1a\n")
                    ocr_raw = ""
                    guess = ""
                    if ok and body:
                        path = out_dir / f"sample{i}-{name}.png"
                        path.write_bytes(body)
                        try:
                            solved = await solve_captcha_image(body, mode="ppllocr")
                            ocr_raw = solved["text"]
                            guess = best_captcha_guess(ocr_raw)
                        except Exception as e:
                            ocr_raw = f"error: {e}"
                    methods[name] = {
                        "ok": ok,
                        "bytes": len(body) if body else 0,
                        "ocr_raw": ocr_raw,
                        "ocr_len": len(normalize_captcha_text(ocr_raw)) if ocr_raw and not ocr_raw.startswith("error") else 0,
                        "guess": guess,
                        "elapsed_ms": int((time.time() - started) * 1000),
                    }
                except Exception as e:
                    methods[name] = {"ok": False, "error": str(e)}

            rows.append({"sample": i, "img_src": src, "captcha_hash": captcha_hash[:12], "methods": methods})

            # refresh for next sample
            img = page.locator('img.captcha, img[src*="/captcha/image/"]').first
            if await img.count():
                await img.click()
                await page.wait_for_timeout(900)

        await browser.close()

    return {"proxy": proxy.display if proxy else "direct", "samples": rows, "out_dir": str(out_dir)}


def main() -> int:
    p = argparse.ArgumentParser(description="Probe idgod captcha images over Tor/proxy")
    p.add_argument("--tor", action="store_true")
    p.add_argument("--proxy", action="append", default=[])
    p.add_argument("--proxy-file")
    p.add_argument("--samples", type=int, default=5)
    p.add_argument("--out-dir", default=str(Path.home() / ".cache/idgod-order-cli/captcha-probe"))
    p.add_argument("--headed", action="store_true")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    proxy = None
    tor_mgr = TorManager()
    try:
        if args.tor:
            proxy = tor_mgr.start()
        elif args.proxy_file:
            proxies = load_proxies_from_file(Path(args.proxy_file))
            proxy = proxies[0] if proxies else None
        elif args.proxy:
            proxy = parse_proxy_line(args.proxy[0])

        result = asyncio.run(
            probe(proxy, samples=args.samples, out_dir=Path(args.out_dir), headed=args.headed)
        )
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"Proxy: {result['proxy']}")
            print(f"Images: {result['out_dir']}")
            for row in result["samples"]:
                print(f"\nSample {row['sample']} hash={row['captcha_hash']} src={row['img_src']}")
                for method, info in row["methods"].items():
                    print(f"  {method}: ok={info.get('ok')} ocr={info.get('ocr_raw')} guess={info.get('guess')}")
        return 0
    finally:
        tor_mgr.stop()


if __name__ == "__main__":
    raise SystemExit(main())
