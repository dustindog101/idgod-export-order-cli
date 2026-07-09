# idgod-order-cli

Submit ID orders to [idgod.ph](https://www.idgod.ph/order) from CSV/XLSX/JSON exports.

> **For AI agents:** Start with [HANDOFF.md](HANDOFF.md) and [AGENTS.md](AGENTS.md).  
> **GitHub:** https://github.com/dustindog101/idgod-order-cli

**Requires a proxy** — idgod.ph blocks direct connections from many IPs. Use Webshare proxies, `--proxy-file`, or `--tor`.

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
3. Enter email + shipping — **not yet automated**
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
