#!/usr/bin/env python3
"""Verify vendor export: parse columns, download per-row images, browser upload sizes."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import re
import sys
from pathlib import Path

from playwright.async_api import async_playwright

from idgod_order_cli.orderer import ORDER_URL, USER_AGENT, IdGodOrderer, _resolve_image
from idgod_order_cli.parser import parse_file
from idgod_order_cli.selectors import SELECTORS
from idgod_order_cli.states import map_eye_color, map_hair_color, map_sex, parse_height

UUID_RE = re.compile(
    r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
    re.I,
)


def _asset_id(url: str) -> str:
    match = UUID_RE.search(url or "")
    return match.group(1).lower() if match else ""


async def _file_input_meta(page, selector: str) -> list[dict]:
    return await page.evaluate(
        """(sel) => {
          const el = document.querySelector(sel);
          if (!el || !el.files || !el.files.length) return [];
          return Array.from(el.files).map((f) => ({
            name: f.name,
            size: f.size,
            type: f.type,
          }));
        }""",
        selector,
    )


async def verify_person_upload(
    page,
    orderer: IdGodOrderer,
    person,
    *,
    proxy,
) -> dict:
    photo_path = await _resolve_image(person.photo, orderer.fallback_photo, proxy)
    sig_path = await _resolve_image(person.signature, orderer.fallback_signature, proxy)
    expected_photo = photo_path.stat().st_size
    expected_sig = sig_path.stat().st_size

    state_options = await orderer._get_state_options(page)
    from idgod_order_cli.states import pick_state_option

    chosen, _ = pick_state_option(
        person.state,
        state_options,
        variant=person.state_variant or orderer.state_variants.get(person.state, ""),
        cheapest=orderer.cheapest_state,
    )
    if chosen is None:
        raise RuntimeError(f"No state option for {person.state}")

    feet, inches = parse_height(person.height or "5'6\"")
    await orderer._fill_sel(page, "first_name", person.first_name)
    if person.middle_name:
        await orderer._fill_sel(page, "middle_name", person.middle_name)
    await orderer._fill_sel(page, "last_name", person.last_name)
    await orderer._fill_sel(page, "date_of_birth", person.dob)
    await orderer._select_sel(page, "state", label=chosen.label)
    await orderer._fill_sel(page, "height_feet", feet)
    await orderer._fill_sel(page, "height_inches", inches)
    await orderer._fill_sel(page, "weight", person.weight or "130")
    await orderer._select_sel(page, "eyes", label=map_eye_color(person.eye_color or "Brown"))
    await orderer._select_sel(page, "hair", label=map_hair_color(person.hair_color or "Brown"))
    await orderer._select_sel(page, "gender", label=map_sex(person.sex or "Female"))
    if person.street:
        await orderer._fill_sel(page, "address1", person.street)
    await orderer._fill_sel(page, "city", person.city)
    await orderer._fill_sel(page, "zip", person.zip)

    await page.locator(SELECTORS["picture"]).set_input_files(str(photo_path))
    await page.locator(SELECTORS["signature"]).set_input_files(str(sig_path))

    photo_meta = await _file_input_meta(page, SELECTORS["picture"])
    sig_meta = await _file_input_meta(page, SELECTORS["signature"])

    photo_ok = bool(photo_meta) and photo_meta[0]["size"] == expected_photo
    sig_ok = bool(sig_meta) and sig_meta[0]["size"] == expected_sig

    return {
        "name": person.display_name,
        "photo_asset": _asset_id(person.photo),
        "sig_asset": _asset_id(person.signature),
        "photo_bytes": expected_photo,
        "sig_bytes": expected_sig,
        "photo_sha256": hashlib.sha256(photo_path.read_bytes()).hexdigest()[:12],
        "sig_sha256": hashlib.sha256(sig_path.read_bytes()).hexdigest()[:12],
        "photo_upload_ok": photo_ok,
        "sig_upload_ok": sig_ok,
        "photo_meta": photo_meta,
        "sig_meta": sig_meta,
    }


async def run(path: Path, *, tor: bool, limit: int) -> int:
    people = parse_file(path)
    if limit > 0:
        people = people[:limit]

    print(f"Parsed {len(people)} row(s) from {path.name}\n")

    orderer = IdGodOrderer(use_tor=tor, headless=True)
    proxy = await orderer._resolve_proxy()

    photo_hashes: set[str] = set()
    for person in people:
        photo_path = await _resolve_image(person.photo, orderer.fallback_photo, proxy)
        sig_path = await _resolve_image(person.signature, orderer.fallback_signature, proxy)
        photo_hash = hashlib.sha256(photo_path.read_bytes()).hexdigest()
        photo_hashes.add(photo_hash)
        print(
            f"  {person.display_name}: photo {_asset_id(person.photo)[:8]}… "
            f"({photo_path.stat().st_size:,} B)  sig {_asset_id(person.signature)[:8]}… "
            f"({sig_path.stat().st_size:,} B)"
        )

    if len(photo_hashes) != len(people):
        print("\nFAIL: duplicate photo content across rows")
        return 1

    print("\nBrowser upload check (no submit)…\n")
    async with async_playwright() as pw:
        browser = await orderer._launch_browser(pw)
        context = await browser.new_context(user_agent=USER_AGENT, viewport={"width": 1400, "height": 900})
        page = await context.new_page()
        page.set_default_timeout(orderer.timeout_ms)

        all_ok = True
        for i, person in enumerate(people):
            await page.goto(ORDER_URL, wait_until="domcontentloaded", timeout=orderer.timeout_ms)
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(1200)
            result = await verify_person_upload(page, orderer, person, proxy=proxy)
            status = "OK" if result["photo_upload_ok"] and result["sig_upload_ok"] else "FAIL"
            print(
                f"  [{status}] {result['name']}: "
                f"photo {result['photo_bytes']:,} B sha {result['photo_sha256']} "
                f"sig {result['sig_bytes']:,} B sha {result['sig_sha256']}"
            )
            if status != "OK":
                all_ok = False
                print(f"         photo meta: {result['photo_meta']}")
                print(f"         sig meta:   {result['sig_meta']}")

        await browser.close()
        orderer._tor_mgr.stop()

    if all_ok:
        print("\nAll per-row images downloaded and attached correctly.")
        return 0
    print("\nUpload verification failed.")
    return 1


def main() -> int:
    p = argparse.ArgumentParser(description="Verify vendor XLSX image links per person")
    p.add_argument("file", type=Path)
    p.add_argument("--tor", action="store_true")
    p.add_argument("--limit", type=int, default=0)
    args = p.parse_args()
    return asyncio.run(run(args.file, tor=args.tor, limit=args.limit))


if __name__ == "__main__":
    sys.exit(main())
