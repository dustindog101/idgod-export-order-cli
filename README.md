# idgod-order-cli

Submit IDGod orders from spreadsheet exports (CSV / XLSX / JSON).

> **Repo:** https://github.com/dustindog101/idgod-export-order-cli  
> **Docs:** [docs/DOCUMENTATION.md](docs/DOCUMENTATION.md) · **Agents:** [HANDOFF.md](HANDOFF.md)

## Install

```bash
cd ~/Projects/idgod-order-cli
pip install -e '.[captcha]'
playwright install chromium   # only if using --playwright
```

## Run

```bash
./idgod-order order orders.xlsx \
  --tor \
  -e you@email.com \
  --fallback-photo ~/Desktop/good.jpg   # optional backup if export URLs expire
```

One command: each row → ID form → cart → coupon → captcha → BTCPay invoice.

- **HTTP** is the default (fast).
- Add **`--playwright`** if HTTP captcha keeps failing.
- Use **`--discount ""`** for no coupon.
- Omit **`--fallback-photo`** when export image URLs are live.

## Commands

```bash
./idgod-order order FILE …       # Place order(s)
./idgod-order probe --tor        # Test connectivity
./idgod-order cache list         # Past run logs
./idgod-order invoice <id>       # Look up BTCPay invoice
./idgod-order order --help       # All flags
```

## Coupon
 
Discount shows on the **BTCPay invoice**, not the cart total.
 
| Flag | Effect |
|------|--------|
| `--discount <code>` | Apply coupon code |
| `--discount ""` | No coupon (default) |
| `--no-require-coupon` | Try coupon but allow full-price checkout |

## Planned: payment tracking

Mark orders paid and upload payment receipts — see [docs/INVOICE-TRACKING.md](docs/INVOICE-TRACKING.md).

## Tests

```bash
pip install -e '.[dev]'
pytest tests/ -q
```

## Full guide

[docs/GUIDE.md](docs/GUIDE.md) — payment methods, shipping, captcha, JSON output, troubleshooting.
