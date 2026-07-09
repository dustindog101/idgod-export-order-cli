#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from .models import Person
from .orderer import IdGodOrderer, DEFAULT_DISCOUNT, ORDER_URL
from .parser import parse_file, person_from_flags
from .proxies import (
    ProxyConfig,
    TorManager,
    load_proxies_from_file,
    parse_proxy_line,
    test_proxy_httpx,
    test_proxy_playwright,
)


def _add_proxy_args(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--proxy",
        action="append",
        default=[],
        metavar="HOST:PORT[:USER:PASS]",
        help="Proxy (repeatable). Formats: host:port or host:port:user:pass or http://user:pass@host:port",
    )
    p.add_argument("--proxy-file", help="File with one proxy per line")
    p.add_argument("--tor", action="store_true", help="Route via Tor (system tor, tor binary, or embedded torpy)")
    p.add_argument(
        "--no-auto-proxy",
        action="store_true",
        help="Use first proxy only; do not failover across list",
    )


def _collect_proxies(args: argparse.Namespace) -> list[ProxyConfig]:
    proxies: list[ProxyConfig] = []
    for item in args.proxy:
        proxies.append(parse_proxy_line(item))
    if args.proxy_file:
        proxies.extend(load_proxies_from_file(Path(args.proxy_file)))
    return proxies


def _add_person_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("file", nargs="?", help="CSV, XLSX, or JSON export file")
    p.add_argument("--file", "-f", dest="file_flag", help="Input file (alternative to positional)")
    p.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    p.add_argument("--dry-run", action="store_true", help="Validate and plan without submitting")
    p.add_argument("--headed", action="store_true", help="Show browser window")
    p.add_argument("--yes", "-y", action="store_true", help="Skip confirmation prompt")
    p.add_argument("--discount", default=DEFAULT_DISCOUNT, help=f"Discount code (default: {DEFAULT_DISCOUNT})")
    p.add_argument("--cheapest-state", action="store_true", help="Auto-pick cheapest state variant")
    p.add_argument(
        "--state-variant",
        action="append",
        default=[],
        metavar="STATE=VARIANT",
        help='Force variant, e.g. --state-variant "Washington=Washington"',
    )
    p.add_argument("--fallback-photo", default="", help="Local image when export photo URL is dead")
    p.add_argument("--fallback-signature", default="", help="Local signature when export URL is dead")
    p.add_argument("--timeout", type=int, default=60, help="Page timeout seconds (default: 60)")
    p.add_argument("--limit", type=int, default=0, help="Max people to submit from file (0=all)")
    p.add_argument("--first-name")
    p.add_argument("--middle-name", default="")
    p.add_argument("--last-name")
    p.add_argument("--state")
    p.add_argument("--dob")
    p.add_argument("--issue-date", default="")
    p.add_argument("--street", default="")
    p.add_argument("--city")
    p.add_argument("--zip")
    p.add_argument("--sex", default="")
    p.add_argument("--height", default="")
    p.add_argument("--weight", default="")
    p.add_argument("--eye-color", default="")
    p.add_argument("--hair-color", default="")
    p.add_argument("--photo", default="")
    p.add_argument("--signature", default="")


def build_parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="idgod-order",
        description="Submit ID orders to idgod.ph from CSV/XLSX/JSON exports or CLI flags.",
    )
    sub = root.add_subparsers(dest="command")

    order_p = sub.add_parser("order", help="Submit order(s)", formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  idgod-order order orders.xlsx --proxy-file proxies/webshare.txt --fallback-photo ~/Desktop/good.jpg
  idgod-order order --tor --headed -y orders.xlsx --fallback-photo ~/Desktop/good.jpg
  idgod-order order --proxy 31.56.127.193:7684:xupznkqu:nn697wqma9r6 --limit 1 -y --json
""")
    _add_person_args(order_p)
    _add_proxy_args(order_p)

    probe_p = sub.add_parser("probe", help="Test proxy/Tor connectivity to idgod.ph")
    probe_p.add_argument("--json", action="store_true")
    probe_p.add_argument("--timeout", type=int, default=25)
    probe_p.add_argument("--url", default=ORDER_URL)
    probe_p.add_argument("--method", choices=["playwright", "httpx", "both"], default="both")
    _add_proxy_args(probe_p)

    # backward compat: `idgod-order orders.xlsx` without subcommand
    _add_person_args(root)
    _add_proxy_args(root)
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
        "Error: provide a file or required flags.\n"
        "  idgod-order order orders.xlsx --proxy-file proxies/webshare.txt --fallback-photo ~/Desktop/good.jpg"
    )


def _print_result(result, as_json: bool) -> None:
    if as_json:
        print(json.dumps(result.to_dict(), indent=2))
        return

    status = "SUCCESS" if result.success else "FAILED"
    print(f"\n=== {status} ===")
    print(result.message)
    if result.proxy_used:
        print(f"Proxy: {result.proxy_used}")
    if result.submitted_ids:
        print(f"Submitted: {', '.join(result.submitted_ids)}")
    if result.total_price is not None:
        print(f"Total: ${result.total_price:.2f}")
    if result.price_per_id is not None:
        print(f"Per ID: ${result.price_per_id:.2f}")
    if result.payment_url:
        print(f"Payment URL: {result.payment_url}")
    if result.payment_info:
        print(f"Payment info:\n{result.payment_info}")
    if result.discount_code:
        applied = "yes" if result.discount_applied else "no"
        print(f"Discount '{result.discount_code}' applied: {applied}")
    for o in result.order_results:
        mark = "ok" if o.success else "FAIL"
        print(f"  [{mark}] {o.person.display_name} ({o.state_selected or o.person.state}): {o.message}")


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
                # default to bundled webshare list
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
            if r.get("form_fields") is not None:
                line += f" fields={r['form_fields']}"
            if r.get("error"):
                line += f" error={r['error']}"
            line += f" ({r.get('elapsed_ms', '?')}ms)"
            print(line)

    return 0 if any(r.get("ok") for r in results) else 1


async def _cmd_order(args: argparse.Namespace) -> int:
    people = _load_people(args)

    if not args.yes and not args.dry_run:
        names = ", ".join(p.display_name for p in people)
        print(f"About to submit {len(people)} ID(s) to idgod.ph: {names}")
        print(f"Discount code: {args.discount}")
        if args.tor:
            print("Routing: Tor")
        elif args.proxy or args.proxy_file:
            print(f"Routing: proxy ({len(_collect_proxies(args))} configured)")
        try:
            ans = input("Continue? [y/N] ").strip().lower()
        except EOFError:
            ans = "n"
        if ans not in ("y", "yes"):
            print("Aborted.")
            return 1

    orderer = IdGodOrderer(
        headless=not args.headed,
        discount_code=args.discount,
        fallback_photo=args.fallback_photo,
        fallback_signature=args.fallback_signature,
        cheapest_state=args.cheapest_state,
        state_variants=_parse_state_variants(args.state_variant),
        dry_run=args.dry_run,
        timeout_ms=args.timeout * 1000,
        proxies=_collect_proxies(args),
        use_tor=args.tor,
        auto_proxy=not args.no_auto_proxy,
    )

    result = await orderer.submit(people)
    _print_result(result, args.json)
    return 0 if result.success else 1


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    parser = build_parser()
    # If first arg looks like a file, treat as `order` subcommand
    if argv and not argv[0].startswith("-") and argv[0] not in ("order", "probe"):
        argv = ["order", *argv]
    args = parser.parse_args(argv)
    # Default subcommand when only root-level args used
    if not getattr(args, "command", None):
        args.command = "order"

    if args.command == "probe":
        return asyncio.run(_cmd_probe(args))
    return asyncio.run(_cmd_order(args))


if __name__ == "__main__":
    sys.exit(main())
