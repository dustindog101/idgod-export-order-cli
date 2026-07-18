# Architecture

## Flow

```
Export file (XLSX/CSV/JSON)
        │
        ▼
   parser.py ──► list[Person] + shipping from export
        │
        ▼
   proxies.py ──► Tor / HTTP proxy
        │
        ├──────────────────────────────┐
        ▼                              ▼
   http_submit.py                  orderer.py
   (default transport)             (--playwright)
        │                              │
        ├─ Prefetch images (direct)    ├─ Playwright + Chrome
        ├─ POST /order multipart       ├─ Fill #order-form
        ├─ POST /cart UPDATE (coupon)  ├─ Fill cart + UPDATE
        ├─ OCR captcha → FINISH        ├─ OCR captcha → FINISH
        └─ Follow BTCPay redirect      └─ Scrape BTCPay page
        │                              │
        └──────────────┬───────────────┘
                       ▼
              btcpay.py ──► PaymentDetails
                       ▼
              finalize_coupon_result()  (invoice vs cart)
                       ▼
              cache.py ──► ~/.cache/idgod-order-cli/orders/
                       ▼
              CheckoutResult (JSON / human UI)
```

## Modules

### `cli.py`
- Subcommands: `order`, `probe`, `cache`, `invoice`
- `order` defaults to HTTP; `--browser` / `--playwright` selects Playwright
- Flags: `--email`, `--discount`, `--no-require-coupon`, `--single-checkout`, etc.

### `http_submit.py`
- `submit_http()` — full HTTP pipeline
- `_solve_captcha_http()` — OCR + FINISH; **must not** UPDATE cart between OCR and submit
- `_sync_cart_coupon_http()` — coupon before captcha only

### `http_forms.py`
- Parse Django forms from HTML
- `finalize_coupon_result()` — BTCPay invoice is source of truth for coupons
- `captcha_hash_from_image_url()` — pin captcha key to OCR'd image

### `orderer.py`
- `IdGodOrderer` — shared config (shipping, coupon, captcha, cache)
- Playwright path: `_fill_person()`, `_fill_checkout()`, `_solve_and_fill_captcha()`
- Image resolve: export URL first, optional fallback

### `captcha.py`
- ddddocr + ppllocr consensus across image preprocess variants
- `best_captcha_guess()` — trim over-long OCR to 4–6 chars

### `btcpay.py`
- Scrape invoice page: fiat, BTC, address, order number, expiry

### `cache.py`
- Save completed run JSON + `index.jsonl`
- **Planned:** payment status, receipt uploads ([INVOICE-TRACKING.md](INVOICE-TRACKING.md))

### `parser.py`
- Export v1/v2 column aliases → `Person`

### `proxies.py`
- `TorManager`, Webshare proxy parsing, probe helpers

## External dependencies

| Package | Purpose |
|---------|---------|
| httpx | HTTP transport, image fetch, probes |
| playwright | Browser transport (optional) |
| ddddocr / ppllocr | Captcha OCR |
| openpyxl | XLSX parsing |
| Pillow | Image prep, WebP→JPEG |

## idgod.ph technical notes

- Django CSRF: `csrfmiddlewaretoken` on every POST
- Order form: `multipart/form-data`, `action=1` continue / `action=2` checkout
- Cart: `action=update` (fields + coupon) / `action=finish` (captcha + submit)
- Cart `#total` often **unchanged** after coupon UPDATE
- BTCPay invoice fiat reflects real price
- django-simple-captcha: `captcha_0` (hash) + `captcha_1` (guess); **rotates on any form POST**

## Planned extension

See [INVOICE-TRACKING.md](INVOICE-TRACKING.md) — `payment_tracking` on cache records, `orders` CLI subcommands, receipt file storage.
