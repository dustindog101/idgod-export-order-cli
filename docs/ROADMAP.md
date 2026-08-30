# Roadmap

Prioritized work for this repo. Update this file when scope changes.

## P0 — Invoice & payment tracking (next feature)

**Goal:** After placing orders, mark which invoices were paid and attach proof (screenshot, txid, PDF).

See **[INVOICE-TRACKING.md](INVOICE-TRACKING.md)** for the full spec.

Deliverables (suggested order):

1. `payment_status` on cached order records (`unpaid` | `paid` | `expired` | `cancelled`)
2. `idgod-order order mark-paid CACHE_OR_ORDER#` CLI
3. `idgod-order order upload-receipt …` — attach file to cache record
4. `idgod-order orders list --unpaid` / `--paid` filters
5. Optional: small local web admin (Flask/FastAPI) for uploads if CLI is awkward

**Out of scope for v1:** syncing with idgod.ph order status API (none documented); automatic blockchain confirmation.

---

## P1 — Reliability

| Item | Notes |
|------|-------|
| HTTP captcha regression tests | Mock django-simple-captcha hash rotation |
| Playwright fallback when HTTP captcha fails N times | Auto `--playwright` retry |
| Rate-limit guard | Warn before N orders/hour; respect vendor limits |
| `--no-fallback` flag | Fail fast if export image URL dead (today: omit `--fallback-photo`) |

---

## P2 — UX

| Item | Notes |
|------|-------|
| `idgod-order orders` subcommand | Unified list/search (cache + payment status) |
| CSV export of order history | For accounting |
| `--resume` from failed row | Hard — cart is server-side session |
| Interactive state-variant picker | When cheapest guess is wrong |

---

## Done (2026-07)

- HTTP transport as default (~3× faster than Playwright)
- Playwright via `--browser` / `--playwright`
- Full checkout: coupon, captcha, BTCPay scrape
- Coupon verified via **invoice fiat** (not cart `#total`)
- HTTP captcha fix: no cart UPDATE between OCR and FINISH (hash rotation bug)
- Per-person export photo/signature URLs (prefetch direct, upload via Tor)
- Order result cache under `~/.cache/idgod-order-cli/orders/`
- `idgod-order invoice` lookup command
- Export v2 format, shipping plans, multi-checkout modes
