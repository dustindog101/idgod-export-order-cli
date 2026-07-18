# idgod-order-cli — full guide

Complete reference for placing orders on idgod.ph from spreadsheet exports.

## Quick start

```bash
cd ~/Projects/idgod-order-cli
pip install -e '.[captcha]'

./idgod-order order ~/Downloads/orders-2026-07-08.xlsx \
  --tor \
  --email you@proton.me \
  --fallback-photo ~/Desktop/good.jpg \
  --fallback-signature ~/Desktop/good.jpg
```

That single command:

1. Reads every row in the spreadsheet as a separate ID
2. Fills each ID order form and adds it to the cart
3. Fills checkout (shipping from the `Shipping` column, email from `--email`)
4. Applies coupon `hartlr` (default)
5. Solves the captcha and clicks FINISH ORDER
6. Scrapes the BTCPay page and prints the BTC invoice link + address

Use `--dry-run` to validate the file without opening a browser.

---

## Commands

| Command | Purpose |
|---------|---------|
| `idgod-order order FILE …` | Full order (HTTP default) |
| `idgod-order probe --tor` | Test Tor/proxy connectivity |
| `idgod-order cache list` | Past run results (read-only log) |
| `idgod-order invoice ID` | Look up BTCPay invoice by id or URL |

---

## Transport

| Mode | Flag | When to use |
|------|------|-------------|
| **HTTP** (default) | *(none)* | Fast; ~15–35s for 4 IDs |
| **Playwright** | `--browser` or `--playwright` | HTTP captcha failing; visual debug (`--headed`) |

Both paths share the same coupon logic and BTCPay invoice scrape.

---

## Where every field comes from

### Per-person ID form (`/order`) — one spreadsheet row each

| Export column | Form field |
|---------------|------------|
| State | State dropdown (see [State ID types](#state-id-types)) |
| First / Middle / Last Name | Name fields |
| DOB | Date of birth |
| Issue Date | Custom license number (if field exists) |
| Street, City, ZIP | ID address (e.g. Seattle — **not** shipping) |
| Sex, Height, Weight | Physical details |
| Eye Color, Hair Color | Appearance |
| Photo URL | ID photo upload |
| Signature URL | Signature upload |

CLI overrides: `--fallback-photo`, `--fallback-signature` when URLs expire. **Omit both** to use export URLs only (order fails if a URL is dead).

### Shared checkout (`/cart`) — whole order

| Source | Cart field |
|--------|------------|
| `Shipping` column | Recipient name, street, city, state, ZIP |
| `--email` | Email (required — payment instructions sent here) |
| `--shipping` or `--shipping-*` | Override parsed shipping |
| Default | Payment: **Bitcoin** |
| Default | Shipping speed: **standard** (~20 days, $20) |
| `--discount` | Coupon code (default `hartlr`; use `""` for none) |
| `--no-require-coupon` | Allow checkout at full price if coupon missing on invoice |

### Coupon behaviour

idgod.ph often keeps cart `#total` unchanged after UPDATE. The **BTCPay invoice fiat** is authoritative:

| IDs | Cart | Invoice with `hartlr` | Full price |
|-----|------|----------------------|------------|
| 1 | $130 | ~$85 | ~$150 |
| 4 | $480 | ~$260 | ~$500 |

`discount_applied: true` in JSON only when invoice &lt; ~75% of cart total.

---

### Ignored columns (export metadata only)

Order ID, Account, Order Date, Status, Payment, Payment Method, Tracking #, Order Note, Export Note, Order Total.

See [XLSX-COLUMNS.md](XLSX-COLUMNS.md) for the analyzed export layout.

---

## Connection

Use **one** of:

```bash
--tor                          # SOCKS via system Tor (:9050) or spawned tor
--proxy HOST:PORT:USER:PASS    # single HTTP proxy
--proxy-file proxies/list.txt    # first line only
```

Test first:

```bash
./idgod-order probe --tor --method httpx
./idgod-order probe --proxy-file proxies/webshare.txt
```

---

## Payment methods

Pass `--payment-method` with one of:

| Value | On-site label |
|-------|----------------|
| `bitcoin` | Bitcoin (**default**) |
| `litecoin` | Litecoin |
| `card` | Credit/Debit Cards, Apple Pay & Google Pay |

Aliases `apple` and `google` also map to card.

After a successful order you get a **BTCPay invoice URL**, BTC amount, and wallet address in the output (unless `--no-fetch-payment`).

---

## Shipping methods (priority)

Pass `--shipping-method` with one of:

| Value | Speed | Price |
|-------|-------|-------|
| `standard` | ~20 business days | $20 (**default**) |
| `express` | ~10–14 days | $50 |
| `super` | ~5–8 days | $120 (≤10 people) |
| `group` | batch tier | $200 (10–30 people) |

Aliases: `economy`, `20` → standard; `50` → express; `120` → super.

---

## State ID types

idgod often lists **multiple dropdown options** per state, e.g.:

- `Washington`
- `Washington Polycarbonate - Official State Material`
- `Washington - Provisional Driver License`

Prices differ. **Default behaviour:** if you do not pass `--state-variant`, the CLI **automatically picks the cheapest** option that matches the state name in your spreadsheet.

To force a specific option:

```bash
--state-variant "Washington=Washington"
--state-variant "California=California Polycarbonate - Official State Material"
```

Repeat `--state-variant` for multiple states.

---

## Required flags for a real order

| Flag | Why |
|------|-----|
| Spreadsheet file | Data source |
| `--email` | Checkout email — not in export |
| `--fallback-photo` | Backup when Cloudflare/R2 photo URLs expire |

Recommended: `--fallback-signature` too.

---

## Output modes

### Human (default)

Live progress on stderr (routing, forms, captcha attempts).  
Final summary on stdout with invoice, BTC address, totals.

### JSON

```bash
./idgod-order order … --json 2>/dev/null
```

Includes `payment_details`, `events` (step log), `captcha`, `orders`, `cache_path`.

### Verbose

`-v` adds per-person detail and timings in the final summary.

---

## Caching

Each run saves a JSON result to:

```
~/.cache/idgod-order-cli/orders/
```

```bash
./idgod-order cache list
```

This is a **read-only log** of past invoices and outcomes — not a resumable browser session.

**Planned:** mark orders paid and upload payment receipts — see [INVOICE-TRACKING.md](INVOICE-TRACKING.md).

---

## Captcha

Handled automatically: **ddddocr + ppllocr** on raw and enhanced images (scaled, contrast, binary), with consensus voting. Default **15 tries**; a new image is fetched only after a rejected guess.

```bash
pip install -e '.[captcha]'   # includes ddddocr + Pillow
```

Debug images saved to `~/.cache/idgod-order-cli/captcha-debug/`.

| Override | Use when |
|----------|----------|
| `--captcha-attempts 20` | More retries (fresh image each time) |
| `--captcha-solver 2captcha` | Hard captchas; needs `TWOCAPTCHA_API_KEY` |
| `--headed --captcha-solver manual` | Type it yourself |

---

## Examples

### One person test (Tor)

```bash
./idgod-order order orders.xlsx \
  --tor --limit 1 \
  --email you@proton.me \
  --fallback-photo ~/Desktop/good.jpg
```

### All rows, Webshare proxy

```bash
PROXY=$(head -1 proxies/webshare.txt)
./idgod-order order orders.xlsx \
  --proxy "$PROXY" \
  --email you@proton.me \
  --fallback-photo ~/Desktop/good.jpg
```

### Express shipping + Litecoin

```bash
./idgod-order order orders.xlsx --tor --email you@proton.me \
  --fallback-photo ~/Desktop/good.jpg \
  --shipping-method express \
  --payment-method litecoin
```

### Parse only

```bash
./idgod-order order orders.xlsx --dry-run
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Chrome won't launch in Cursor | Run from **Terminal.app** |
| Captcha keeps failing | Try `--tor` with auto solver; or 2captcha; check `captcha-debug/` PNGs |
| Photo URL failed | Set `--fallback-photo` |
| Multiple state options error | Should not happen with default cheapest; or pass `--state-variant` |
| Empty cart on probe | Captcha only appears with items in cart |

See also [TESTING.md](TESTING.md), [KNOWN-ISSUES.md](KNOWN-ISSUES.md), [CART-FORM.md](CART-FORM.md).

---

## Tests

```bash
pip install -e '.[dev]'
pytest tests/ -v
```
