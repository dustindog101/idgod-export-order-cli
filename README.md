# idgod-order-cli

Submit IDGod orders from spreadsheet exports (CSV / XLSX / JSON).

> **Repo:** https://github.com/dustindog101/idgod-export-order-cli  
> **Full guide:** [docs/GUIDE.md](docs/GUIDE.md) · **Agents:** [HANDOFF.md](HANDOFF.md)

## Install

```bash
pip install -e '.[captcha]'
playwright install chromium   # first time only
```

## Run

```bash
./idgod-order order orders.xlsx \
  --tor \
  --email you@proton.me \
  --fallback-photo ~/Desktop/good.jpg
```

One command: each spreadsheet row → ID form → cart → coupon → captcha → BTCPay invoice.

## Help

```bash
./idgod-order order --help
```

Shows examples, payment/shipping options, and defaults. Detailed docs live in **[docs/GUIDE.md](docs/GUIDE.md)**.

## Other commands

```bash
./idgod-order probe --tor
./idgod-order cache list
./idgod-order order orders.xlsx --dry-run
```

## Tests

```bash
pip install -e '.[dev]'
pytest tests/ -v
```
