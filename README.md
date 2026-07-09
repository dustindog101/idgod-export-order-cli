# idgod-order-cli

Submit ID orders to [idgod.ph](https://www.idgod.ph/order) from CSV/XLSX/JSON exports.

> **For AI agents:** [HANDOFF.md](HANDOFF.md) · **Not** [idgod-order-cli](https://github.com/dustindog101/idgod-order-cli) — [docs/REPO-NOT-OTHER.md](docs/REPO-NOT-OTHER.md)  
> **Repo:** https://github.com/dustindog101/idgod-export-order-cli

**Requires a proxy** — idgod.ph blocks direct connections from many IPs.

## Full workflow (verified)

```bash
./idgod-order order --file ~/Downloads/orders-2026-07-08.xlsx \
  --proxy-file proxies/webshare.txt \
  --fallback-photo ~/Desktop/good.jpg \
  --fallback-signature ~/Desktop/good.jpg \
  --state-variant "Washington=Washington" \
  --checkout --email you@proton.me \
  -y --json
```

This will:
1. Add all IDs to cart ($120/ID for 4+ WA orders in test)
2. Fill shipping from export `Shipping` column
3. Set payment to Bitcoin, shipping to standard $20
4. Apply coupon `hartlr` and click UPDATE

**Manual step:** Open cart in browser (`--headed`), solve captcha, click **FINISH ORDER**.

## Install

```bash
cd ~/Projects/idgod-order-cli
python3 -m venv .venv
.venv/bin/pip install -e .
# Uses system Chrome if bundled Chromium mismatches your arch
```

## Quick start

```bash
# Test proxy connectivity
./idgod-order probe --proxy-file proxies/webshare.txt --json

# Dry-run your spreadsheet
./idgod-order order --file ~/Downloads/orders-2026-07-08.xlsx \
  --fallback-photo ~/Desktop/good.jpg --dry-run -y --json

# Dry-run with checkout shipping parsed from the export Shipping column
./idgod-order order --file ~/Downloads/orders-2026-07-08.xlsx \
  --fallback-photo ~/Desktop/good.jpg \
  --checkout --email you@example.com --dry-run -y --json

# Submit all 4 IDs (tested working via Seattle proxy)
./idgod-order order --file ~/Downloads/orders-2026-07-08.xlsx \
  --proxy 31.56.127.193:7684:xupznkqu:nn697wqma9r6 \
  --fallback-photo ~/Desktop/good.jpg \
  --fallback-signature ~/Desktop/good.jpg \
  --state-variant "Washington=Washington" -y --json
```

## Proxy options

| Flag | Description |
|------|-------------|
| `--proxy HOST:PORT:USER:PASS` | Single proxy (repeatable) |
| `--proxy-file PATH` | One proxy per line |
| `--tor` | Use Tor (system daemon, `tor` binary, or embedded torpy) |
| `--no-auto-proxy` | Don't failover; use first proxy only |

Proxy file format:
```
31.56.127.193:7684:xupznkqu:nn697wqma9r6
http://user:pass@host:port
```

Bundled list: `proxies/webshare.txt`

## Commands

- `idgod-order probe` — test proxies against idgod.ph
- `idgod-order order` — submit orders (default)

## Checkout options

`--checkout` fills checkout email and shipping fields after the cart is created. It reads the first non-empty export `Shipping` column automatically, or you can override with:

```bash
--email you@example.com
--shipping "Name, Street, City, ST, ZIP, USA"
--shipping-name "Name" --shipping-street "Street" --shipping-city "City" \
--shipping-state "ST" --shipping-zip "ZIP"
```

Optional selectors:
- `--payment-method Bitcoin`
- `--shipping-method "USPS"`
- `--checkout-submit` clicks the checkout/continue button after filling fields. It does not submit payment.
- `--debug-dir ./debug-checkout` writes cart/checkout HTML plus form control metadata for troubleshooting.

## What the site asks for

| Field | Required | From your export |
|-------|----------|------------------|
| First/Last name | Yes | Yes |
| Middle name | No | Yes |
| Date of birth | Yes | DOB |
| State | Yes | State (dropdown) |
| Height ft/in, Weight | Yes | Height, Weight |
| Eyes, Hair, Gender | Yes | Eye Color, Hair Color, Sex |
| City, Zip | Yes | Yes |
| Address on ID | No | Street |
| Photo | Yes | Photo URL or `--fallback-photo` |
| Signature | No | Signature URL or fallback |
| DL#/issue date | No (+$20) | Issue Date |

**Never uploaded:** Order ID, Account, Payment, Shipping, Order Total, etc.

## Discount code `hartlr`

The site has **no coupon field** on order/cart pages. Discount codes are applied manually — email idgod@idgod.ph with your order number. The CLI passes `--discount` for reference but cannot auto-apply it.

## Payment flow

1. Items added to cart → checkout page at `/cart`
2. Select payment method (Bitcoin, Litecoin, Card)
3. Enter email + shipping with `--checkout`
4. Payment instructions emailed within ~4 hours

## Test results (2026-07-09)

Via proxy `31.56.127.193:7684` (US Seattle):

| Metric | Result |
|--------|--------|
| Spreadsheet rows | 4/4 submitted |
| State selected | Washington |
| Cart total | **$480.00** |
| Per ID | **$120.00** |
| Payment URL | https://www.idgod.ph/cart |
| Discount `hartlr` | Not auto-applied (no field on site) |
| Proxy required | Yes (direct connection reset) |

## Test results (2026-07-09, checkout dry run)

Command:

```bash
./idgod-order order --file /Users/king/Downloads/orders-2026-07-08.xlsx \
  --fallback-photo /Users/king/Desktop/good.jpg \
  --checkout --email test@example.com --dry-run -y --json
```

Result:
- `success: true`
- `cart_count: 4`
- `checkout_attempted: true`
- Parsed shipping: `Anaya Samsotha-Cooley, 5125 Leona St, Oakland, CA, 94619, USA`
