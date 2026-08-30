# Agent Handoff — idgod-order-cli

**Read this first.** Full context for continuing work without re-discovering the project.

## Project location

```
/Users/king/Projects/idgod-order-cli
```

## GitHub

> **⚠️ [docs/REPO-NOT-OTHER.md](docs/REPO-NOT-OTHER.md)** — this is **NOT** `dustindog101/idgod-order-cli` (different project).

| | |
|---|---|
| **Account** | `dustindog101` |
| **Repo** | https://github.com/dustindog101/idgod-export-order-cli |
| **Active branch** | `feat/http-orderer` (HTTP default; merge to `main` when ready) |
| **Commit author** | `mufasa dev <56493866+dustindog101@users.noreply.github.com>` |

See [docs/GITHUB.md](docs/GITHUB.md) for clone/push workflow.

## What this tool does

Python CLI that reads ID order exports (CSV/XLSX/JSON) and submits them to **https://www.idgod.ph/order**, then completes checkout on **/cart** through BTCPay.

**Default transport:** HTTP (fast, no browser). **Fallback:** `--browser` / `--playwright`.

One `order` command: row → ID form → cart → coupon → captcha → BTCPay invoice.

## Current status (2026-07-18)

| Area | Status |
|------|--------|
| Parse XLSX/CSV/JSON (v1 + v2 export) | ✅ |
| HTTP order + checkout | ✅ Default |
| Playwright order + checkout | ✅ `--playwright` |
| Per-person photo/signature from export URLs | ✅ Prefetch direct, upload via Tor |
| Coupon handling | ✅ Verified on BTCPay invoice fiat |
| Coupon detection | ✅ `finalize_coupon_result()` — invoice fiat authoritative, not `#total` |
| HTTP captcha | ✅ Fixed: no cart UPDATE between OCR and FINISH (hash rotation bug) |
| Order result cache | ✅ `~/.cache/idgod-order-cli/orders/` |
| Invoice lookup | ✅ `idgod-order invoice <id>` |
| **Payment tracking / receipt uploads** | ❌ **Next feature** — see [docs/INVOICE-TRACKING.md](docs/INVOICE-TRACKING.md) |

## Critical environment facts

1. **Use Tor or proxy** — direct idgod.ph often fails (`connection reset`).
2. **Coupon applies on BTCPay invoice**, not cart `#total`.
3. **Do not spam test orders** — vendor monitors for excessive test checkouts. Ask before bulk live runs.
4. **Export photo URLs** — R2 signed URLs work; omit `--fallback-photo` when URLs are live.
5. **HTTP captcha** — never call `_sync_cart_coupon_http()` between OCR and FINISH POST.

## Verified commands

```bash
cd /Users/king/Projects/idgod-order-cli
pip install -e '.[captcha]'

# Dry run
./idgod-order order tests/fixtures/synthetic-2-ids.json --dry-run -y

# Full order — HTTP
./idgod-order order tests/fixtures/synthetic-2-ids.json \
  --tor \
  -e test@example.com \
  -y --json --single-checkout

# Playwright fallback if HTTP captcha struggles
./idgod-order order … --playwright …

# With coupon
./idgod-order order … --discount "PROMO"

# Allow full-price checkout if coupon fails
./idgod-order order … --no-require-coupon
```

## File map

```
idgod-order-cli/
├── HANDOFF.md              ← you are here
├── AGENTS.md               ← agent rules
├── README.md               ← user quick start
├── docs/
│   ├── DOCUMENTATION.md    ← doc index
│   ├── GUIDE.md            ← full CLI reference
│   ├── INVOICE-TRACKING.md ← NEXT FEATURE spec
│   ├── ROADMAP.md
│   ├── ARCHITECTURE.md
│   └── …
├── idgod_order_cli/
│   ├── cli.py              ← order, probe, cache, invoice commands
│   ├── http_submit.py      ← HTTP transport + captcha
│   ├── http_forms.py       ← form parse, coupon/invoice logic
│   ├── orderer.py          ← Playwright + shared IdGodOrderer
│   ├── captcha.py          ← OCR (ddddocr, ppllocr, 2captcha)
│   ├── btcpay.py           ← invoice HTML parse
│   ├── cache.py            ← order result persistence
│   ├── parser.py           ← export → Person
│   └── models.py           ← CheckoutResult, etc.
├── scripts/                ← dev probes
└── tests/
```

## Priority tasks for next agent

### P0 — Invoice tracking (user-requested)

Implement [docs/INVOICE-TRACKING.md](docs/INVOICE-TRACKING.md):

1. `payment_tracking` on cache records
2. `orders mark-paid`, `orders upload-receipt`, `orders list --unpaid`
3. Tests in `tests/test_cache.py`

### P1 — Polish

- HTTP captcha unit test (mock hash rotation)
- Auto-retry with `--playwright` after HTTP captcha exhaustion
- Rate-limit warning before live runs

## Coupon logic (do not regress)

```python
# http_forms.py — authoritative check
finalize_coupon_result(code, cart_total, invoice_fiat)
# discount_applied = True only when invoice < cart * 0.75
```

`--no-require-coupon` still applies code but allows checkout at full price.

## Export columns

**ID form:** State, Names, DOB, Issue Date, Street, City, ZIP, Sex, Height, Weight, Eye/Hair, Photo, Signature

**Checkout:** Shipping column + `--email`

**Ignored:** Order ID, Account, Status, Payment, Order Total, etc.

See [docs/XLSX-COLUMNS.md](docs/XLSX-COLUMNS.md).

## Mistakes to avoid

- Do not report `discount_applied: true` when only the coupon field was saved — check invoice.
- Do not run many live test orders without user approval (vendor monitors).
- Do not use `--fallback-photo` when user wants export images only.
- Do not sync cart (UPDATE) between captcha OCR and FINISH on HTTP path.
- Use `./idgod-order` or `.venv/bin/python`, not system Python without deps.

## Documentation

Full index: [docs/DOCUMENTATION.md](docs/DOCUMENTATION.md)

## Contacts / references

- Site: https://www.idgod.ph/order
- Cart: https://www.idgod.ph/cart
- BTCPay: https://btcpay.idgod.ph/
