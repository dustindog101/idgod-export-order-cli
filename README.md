# idgod-order-cli

Submit IDGod orders from spreadsheet exports (v2 JSON/XLSX).

## Install

```bash
pip install -e '.[captcha]'
playwright install chromium   # first time only
```

## Run

```bash
# Simplest — file first, no "order" subcommand needed
./idgod-order orders.xlsx --email you@proton.me --tor

# Same thing, explicit
./idgod-order run orders.xlsx -e you@proton.me --tor

# Validate export only
./idgod-order orders.xlsx --dry-run
```

Shipping is read from the export. Photo/signature URLs are used automatically when present.

## Help

```bash
./idgod-order --help
./idgod-order order --help
```

## Other commands

```bash
./idgod-order check --tor          # test connection
./idgod-order invoice INVOICE_ID   # look up payment
./idgod-order cache                # past results
```

Set `IDGOD_EMAIL` to skip passing `--email` every time.

Full guide: **[docs/GUIDE.md](docs/GUIDE.md)**

## Tests

```bash
pytest tests/ -v
```
