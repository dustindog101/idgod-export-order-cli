#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from .cache import OrderCache, default_cache_dir
from .models import Person, ShippingInfo
from .orderer import IdGodOrderer, DEFAULT_DISCOUNT, ORDER_URL
from .parser import extract_shipping_text, parse_file, parse_shipping_text, person_from_flags
from .proxies import (
    ProxyConfig,
    TorManager,
    load_proxies_from_file,
    parse_proxy_line,
    test_proxy_httpx,
    test_proxy_playwright,
)
from .help_text import (
    ORDER_DESCRIPTION,
    ORDER_EPILOG,
    PAYMENT_CHOICES,
    PAYMENT_HELP,
    ROOT_DESCRIPTION,
    SHIPPING_CHOICES,
    SHIPPING_HELP,
)
from .ui import RunUI, format_result_human


class _OrderHelpFormatter(argparse.RawDescriptionHelpFormatter):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("max_help_position", 36)
        kwargs.setdefault("width", 88)
        super().__init__(*args, **kwargs)


def _add_proxy_args(p: argparse.ArgumentParser) -> None:
    g = p.add_argument_group("connection (use --tor or --proxy)")
    g.add_argument(
        "--proxy",
        action="append",
        default=[],
        metavar="HOST:PORT[:USER:PASS]",
        help="HTTP proxy (repeatable). host:port or host:port:user:pass",
    )
    g.add_argument("--proxy-file", help="File with one proxy per line (uses first line)")
    g.add_argument(
        "--tor",
        action="store_true",
        help="Route via Tor (:9050 / :9150, or spawn tor)",
    )


def _add_person_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("file", nargs="?", help="CSV, XLSX, or JSON export")
    p.add_argument("--file", "-f", dest="file_flag", help="Input file")

    req = p.add_argument_group("required for a real order")
    req.add_argument("--email", default="", help="Checkout email (payment instructions sent here)")
    req.add_argument(
        "--fallback-photo",
        default="",
        help="Local photo if export URL is dead",
    )
    req.add_argument(
        "--fallback-signature",
        default="",
        help="Local signature if export URL is dead",
    )

    ov = p.add_argument_group("overrides")
    ov.add_argument("--limit", type=int, default=0, help="Max rows from file (0 = all)")
    ov.add_argument("--discount", default=DEFAULT_DISCOUNT, help=f"Coupon code (default: {DEFAULT_DISCOUNT})")
    ov.add_argument(
        "--state-variant",
        action="append",
        default=[],
        metavar="STATE=LABEL",
        help="Force a specific ID dropdown label when default cheapest is wrong",
    )
    ov.add_argument(
        "--payment-method",
        choices=PAYMENT_CHOICES,
        default=None,
        help=PAYMENT_HELP,
    )
    ov.add_argument(
        "--shipping-method",
        choices=SHIPPING_CHOICES,
        default=None,
        help=SHIPPING_HELP,
    )
    ov.add_argument("--shipping", default="", help='Override cart shipping, e.g. "Name, St, City, ST, ZIP, USA"')
    ov.add_argument("--shipping-name", default="")
    ov.add_argument("--shipping-street", default="")
    ov.add_argument("--shipping-city", default="")
    ov.add_argument("--shipping-state", default="")
    ov.add_argument("--shipping-zip", default="")
    ov.add_argument("--shipping-country", default="")

    adv = p.add_argument_group("advanced")
    adv.add_argument("--dry-run", action="store_true", help="Parse file only; no browser")
    adv.add_argument("--json", action="store_true", help="Machine-readable JSON (no live progress)")
    adv.add_argument("--headed", action="store_true", help="Show browser window")
    adv.add_argument("-y", "--yes", action="store_true", help="Skip confirmation (auto when piped)")
    adv.add_argument("-v", "--verbose", action="store_true", help="Extra detail in final summary")
    adv.add_argument("--timeout", type=int, default=60, help=argparse.SUPPRESS)
    adv.add_argument("--no-cache", action="store_true", help="Do not save result JSON to cache")
    adv.add_argument("--no-fetch-payment", action="store_true", help="Skip BTCPay invoice scrape")
    adv.add_argument("--debug-dir", default="", help="Save cart/captcha HTML for debugging")
    adv.add_argument("--cache-dir", default="", help=argparse.SUPPRESS)
    adv.add_argument(
        "--captcha-solver",
        choices=["auto", "ppllocr", "ddddocr", "2captcha", "manual"],
        default="auto",
        help=argparse.SUPPRESS,
    )
    adv.add_argument("--captcha-attempts", type=int, default=10, help=argparse.SUPPRESS)
    adv.add_argument("--2captcha-key", dest="twocaptcha_key", default="", help=argparse.SUPPRESS)

    # Single-person mode (no file)
    sp = p.add_argument_group("single person (instead of file)")
    for dest, flag in (
        ("first_name", "--first-name"),
        ("last_name", "--last-name"),
        ("state", "--state"),
        ("dob", "--dob"),
        ("city", "--city"),
        ("zip", "--zip"),
    ):
        sp.add_argument(flag, dest=dest)
    sp.add_argument("--middle-name", default="")
    sp.add_argument("--issue-date", default="")
    sp.add_argument("--street", default="")
    sp.add_argument("--sex", default="")
    sp.add_argument("--height", default="")
    sp.add_argument("--weight", default="")
    sp.add_argument("--eye-color", default="")
    sp.add_argument("--hair-color", default="")
    sp.add_argument("--photo", default="")
    sp.add_argument("--signature", default="")


def build_parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="idgod-order",
        description=ROOT_DESCRIPTION,
        formatter_class=_OrderHelpFormatter,
    )
    sub = root.add_subparsers(dest="command")

    order_p = sub.add_parser(
        "order",
        help="Place order(s): ID forms → cart → checkout → BTCPay",
        description=ORDER_DESCRIPTION,
        formatter_class=_OrderHelpFormatter,
        epilog=ORDER_EPILOG,
    )
    _add_person_args(order_p)
    _add_proxy_args(order_p)

    probe_p = sub.add_parser("probe", help="Test proxy/Tor connectivity to idgod.ph")
    probe_p.add_argument("--json", action="store_true")
    probe_p.add_argument("--timeout", type=int, default=25)
    probe_p.add_argument("--url", default=ORDER_URL)
    probe_p.add_argument("--method", choices=["playwright", "httpx", "both"], default="both")
    _add_proxy_args(probe_p)

    cache_p = sub.add_parser("cache", help="List past order results (not resumable sessions)")
    cache_p.add_argument("cache_action", nargs="?", default="list", choices=["list"])
    cache_p.add_argument("--limit", type=int, default=15)
    cache_p.add_argument("--json", action="store_true")
    cache_p.add_argument("--cache-dir", default="", help=argparse.SUPPRESS)

    return root


def _parse_state_variants(items: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for item in items:
        if "=" in item:
            state, variant = item.split("=", 1)
            out[state.strip()] = variant.strip()
        else:
            out[item.strip()] = item.strip()
    return out


def _load_people(args: argparse.Namespace) -> list[Person]:
    path_str = args.file_flag or args.file
    if path_str:
        people = parse_file(Path(path_str))
        if args.limit and args.limit > 0:
            people = people[: args.limit]
        return people

    if args.first_name and args.last_name and args.state and args.dob and args.city and args.zip:
        return [person_from_flags({
            "first name": args.first_name,
            "middle name": args.middle_name,
            "last name": args.last_name,
            "state": args.state,
            "dob": args.dob,
            "issue date": args.issue_date,
            "street": args.street,
            "city": args.city,
            "zip": args.zip,
            "sex": args.sex,
            "height": args.height,
            "weight": args.weight,
            "eye color": args.eye_color,
            "hair color": args.hair_color,
            "photo": args.photo,
            "signature": args.signature,
        })]

    raise SystemExit(
        "Error: provide a spreadsheet file or single-person flags.\n"
        "  idgod-order order orders.xlsx --tor --email you@proton.me "
        "--fallback-photo ~/Desktop/good.jpg"
    )


def _load_shipping(args: argparse.Namespace, people: list[Person]) -> ShippingInfo:
    path_str = args.file_flag or args.file
    raw_shipping = args.shipping
    if not raw_shipping and path_str:
        raw_shipping = extract_shipping_text(Path(path_str))

    shipping = parse_shipping_text(raw_shipping)
    if args.email:
        shipping.email = args.email
    elif people:
        shipping.email = people[0].email

    if args.shipping_name:
        shipping.name = args.shipping_name
    if args.shipping_street:
        shipping.street = args.shipping_street
    if args.shipping_city:
        shipping.city = args.shipping_city
    if args.shipping_state:
        shipping.state = args.shipping_state
    if args.shipping_zip:
        shipping.zip = args.shipping_zip
    if args.shipping_country:
        shipping.country = args.shipping_country

    return shipping


def _print_result(result, as_json: bool, *, verbose: bool = False) -> None:
    if as_json:
        print(json.dumps(result.to_dict(), indent=2))
        return
    print(format_result_human(result, verbose=verbose))


def _should_skip_confirm(args: argparse.Namespace) -> bool:
    return bool(args.yes or args.dry_run or not sys.stdin.isatty())


async def _cmd_probe(args: argparse.Namespace) -> int:
    results: list[dict] = []
    tor_mgr = TorManager()

    try:
        if args.tor:
            proxy = tor_mgr.start(timeout=args.timeout)
            if args.method in ("httpx", "both"):
                results.append(await test_proxy_httpx(proxy, args.url, args.timeout))
            if args.method in ("playwright", "both"):
                results.append(await test_proxy_playwright(proxy, args.url, args.timeout * 1000))
        else:
            proxies = _collect_proxies(args)
            if not proxies:
                default_file = Path(__file__).resolve().parent.parent / "proxies" / "webshare.txt"
                if default_file.exists():
                    proxies = load_proxies_from_file(default_file)
            if not proxies:
                print("No proxies specified. Use --proxy, --proxy-file, or --tor", file=sys.stderr)
                return 1
            for proxy in proxies:
                if args.method in ("httpx", "both"):
                    results.append(await test_proxy_httpx(proxy, args.url, args.timeout))
                if args.method in ("playwright", "both"):
                    results.append(await test_proxy_playwright(proxy, args.url, args.timeout * 1000))
    finally:
        tor_mgr.stop()

    if args.json:
        print(json.dumps({"url": args.url, "results": results}, indent=2))
    else:
        print(f"Probe results for {args.url}\n")
        for r in results:
            mark = "OK" if r.get("ok") else "FAIL"
            line = f"[{mark}] {r.get('proxy', '?')}"
            if r.get("status"):
                line += f" status={r['status']}"
            if r.get("title"):
                line += f" title={r['title'][:60]!r}"
            if r.get("error"):
                line += f" error={r['error']}"
            line += f" ({r.get('elapsed_ms', '?')}ms)"
            print(line)

    return 0 if any(r.get("ok") for r in results) else 1


def _collect_proxies(args: argparse.Namespace) -> list[ProxyConfig]:
    proxies: list[ProxyConfig] = []
    for item in args.proxy:
        proxies.append(parse_proxy_line(item))
    if args.proxy_file:
        proxies.extend(load_proxies_from_file(Path(args.proxy_file)))
    # Use only the first proxy from a file — use `probe` to test others
    if len(proxies) > 1 and args.proxy_file and not args.proxy:
        proxies = proxies[:1]
    return proxies


async def _cmd_cache(args: argparse.Namespace) -> int:
    cache = OrderCache(args.cache_dir)
    entries = cache.list_entries(limit=args.limit)
    if args.json:
        print(json.dumps({"cache_dir": str(cache.root), "entries": entries}, indent=2))
        return 0
    print(f"Past orders (read-only log): {cache.root}\n")
    if not entries:
        print("(empty)")
        return 0
    for e in entries:
        ids = ", ".join(e.get("submitted_ids", [])[:3])
        total = e.get("total_after_discount")
        total_s = f"${total:.2f}" if total is not None else "?"
        ok = "✓" if e.get("success") else "✗"
        print(f"{ok}  {e.get('saved_at', '?')}  {ids}  {total_s}")
        if e.get("payment_url"):
            print(f"    {e['payment_url']}")
    return 0


async def _cmd_order(args: argparse.Namespace) -> int:
    people = _load_people(args)
    full_order = not args.dry_run

    if full_order and not args.payment_method:
        args.payment_method = "bitcoin"

    shipping = _load_shipping(args, people) if full_order else ShippingInfo()

    if full_order and not shipping.email:
        raise SystemExit(
            "Error: --email is required for checkout (payment instructions are sent there).\n"
            "  idgod-order order orders.xlsx --tor --email you@proton.me ..."
        )

    if not _should_skip_confirm(args):
        names = ", ".join(p.display_name for p in people)
        print(f"Submit {len(people)} ID(s) to idgod.ph: {names}")
        print(f"Coupon: {args.discount} · Email: {shipping.email}")
        routing = "Tor" if args.tor else ("proxy" if (args.proxy or args.proxy_file) else "direct")
        print(f"Route: {routing}")
        try:
            ans = input("Continue? [y/N] ").strip().lower()
        except EOFError:
            ans = "n"
        if ans not in ("y", "yes"):
            print("Aborted.")
            return 1

    path_str = args.file_flag or args.file or ""
    ui = RunUI(json_mode=args.json)
    routing = "Tor" if args.tor else (
        f"proxy" if (args.proxy or args.proxy_file) else "direct"
    )
    if full_order:
        ui.banner(ids=len(people), routing=routing, modes=["checkout", "submit", "payment"])

    state_variants = _parse_state_variants(args.state_variant)
    cheapest_state = len(state_variants) == 0

    orderer = IdGodOrderer(
        headless=not args.headed,
        discount_code=args.discount,
        fallback_photo=args.fallback_photo,
        fallback_signature=args.fallback_signature,
        cheapest_state=cheapest_state,
        state_variants=state_variants,
        dry_run=args.dry_run,
        timeout_ms=args.timeout * 1000,
        proxies=_collect_proxies(args),
        use_tor=args.tor,
        auto_proxy=False,
        checkout=full_order,
        checkout_submit=full_order,
        captcha_solver=args.captcha_solver,
        twocaptcha_key=args.twocaptcha_key,
        captcha_attempts=args.captcha_attempts,
        shipping=shipping,
        payment_method=args.payment_method,
        shipping_method=args.shipping_method,
        debug_dir=args.debug_dir,
        input_file=str(path_str) if path_str else "",
        cache_dir=args.cache_dir,
        use_cache=not args.no_cache,
        fetch_payment=full_order and not args.no_fetch_payment,
        ui=ui,
    )

    result = await orderer.submit(people)
    _print_result(result, args.json, verbose=args.verbose)
    return 0 if result.success else 1


_SUBCOMMANDS = frozenset({"order", "probe", "cache", "-h", "--help"})


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    if argv and argv[0] not in _SUBCOMMANDS:
        argv = ["order", *argv]
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        args.command = "order"

    if args.command == "probe":
        return asyncio.run(_cmd_probe(args))
    if args.command == "cache":
        return asyncio.run(_cmd_cache(args))
    return asyncio.run(_cmd_order(args))


if __name__ == "__main__":
    sys.exit(main())
