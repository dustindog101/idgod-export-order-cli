# HTTP POST vs Playwright — exploration notes

**Branch:** `explore/http-post-order`  
**Probe script:** `scripts/http-post-probe.py`  
**Status:** POC successful for add-to-cart (2026-07-10)

## Question

Can we drop Playwright and use raw `httpx` POST requests for idgod.ph orders?

## Short answer

| Step | HTTP-only? | Notes |
|------|------------|-------|
| GET `/order` + session/CSRF | ✅ Yes | `sessionid` + `csrftoken` cookies |
| POST add-to-cart (`action=1`) | ✅ Yes | Multipart form + photo file |
| GET `/cart` + read total | ✅ Yes | `$110.00` confirmed in live test |
| GET captcha image | ✅ Yes | `/captcha/image/<hash>/` over same session |
| POST cart UPDATE (coupon/shipping) | ⚠️ Likely | Same CSRF rules; not fully tested here |
| POST FINISH ORDER (`action=finish`) | ⚠️ Possible | Needs `captcha_0` + `captcha_1`; OCR already exists in CLI |
| BTCPay redirect / invoice scrape | ⚠️ Maybe | Follow redirects with httpx; parse HTML like today |

**Full browserless checkout is plausible.** Biggest risks are photo validation edge cases and any JS-only validation we haven't hit yet.

## Live test results (Tor, 2026-07-10)

```bash
./scripts/http-post-probe.py --tor --phase full \
  --fixture tests/fixtures/multi-shipping-live.json --json
```

| Phase | Result |
|-------|--------|
| `analyze` | `/order` form parsed: 15 inputs, 4 selects, `picture`+`signature` file fields, Django CSRF |
| `submit` | `POST /order` → **200** in ~1.8s (Washington, real WebP photo from export) |
| `cart` | `/cart` total **`$110.00`**, checkout fields + captcha present |
| `captcha` | PNG fetched (**8375 bytes**) via session cookie |

## Critical requirement: Referer + CSRF headers

First POST attempt returned **403** with:

> CSRF verification failed … requires a “Referer header”

Fix (already in probe script):

- `Referer: https://www.idgod.ph/order`
- `Origin: https://www.idgod.ph`
- `X-CSRFToken: <csrftoken cookie>`
- `csrfmiddlewaretoken` in form body

Without these, Django rejects the request even with a valid session.

## Order form POST shape

Standard Django multipart POST to `https://www.idgod.ph/order`:

| Field | Example |
|-------|---------|
| `csrfmiddlewaretoken` | from GET HTML |
| `first_name`, `last_name`, … | text fields |
| `state` | numeric option value (e.g. `371` = Washington) |
| `eyes`, `hair`, `gender` | coded values (`BRN`, `BLK`, `1`) |
| `picture` | JPEG file (WebP converted) |
| `signature` | optional file |
| `action` | `1` = Add & Continue, `2` = Add & Checkout |

No JavaScript token beyond CSRF. jQuery Bootstrap validator is a **browser UX** issue, not a server requirement — HTTP POST bypasses it entirely.

## Cart checkout POST shape (from live HTML dump)

Cart uses a second form (`#order-form` on `/cart`):

| Field | Purpose |
|-------|---------|
| `name`, `address`, `city`, `state`, `zip`, `country` | Shipping |
| `email` | Payment instructions |
| `payment_method` | `0` Bitcoin, etc. |
| `priority` | Shipping tier (`9` = standard $20) |
| `coupon` | Discount code |
| `captcha_0` | Hidden hash |
| `captcha_1` | User/OCR answer |
| `action` | `update` or `finish` |

Captcha image: `GET /captcha/image/<captcha_0>/` (same cookies).

## Performance vs Playwright

| | Playwright | httpx |
|--|-----------|-------|
| Tor startup | same | same |
| Per ID add-to-cart | ~5–15s (browser launch, DOM, uploads) | **~2s** in probe |
| Memory | Chrome process | minimal |
| Checkout captcha | in-page OCR or manual | download PNG + existing OCR stack |

## Recommended path (if we implement)

1. **Hybrid v1** — httpx for add-to-cart loop; keep Playwright only for checkout until cart POST is proven
2. **Hybrid v2** — httpx for cart UPDATE + captcha fetch + FINISH POST
3. **Full httpx** — drop Playwright dependency if BTCPay follow + invoice parse works

Do **not** replace the production orderer until:

- [ ] Cart UPDATE + coupon applied via HTTP
- [ ] FINISH ORDER + BTCPay redirect via HTTP with OCR captcha
- [ ] WebP/photo rejection cases match Playwright behavior
- [ ] Multi-ID sessions (action=1 repeatedly) verified

## Running the probe

```bash
# Safe: network inspection only
./scripts/http-post-probe.py --tor --phase analyze

# Full POC (adds a real $110 ID to cart — uses export photo URL)
./scripts/http-post-probe.py --tor --phase full \
  --fixture tests/fixtures/multi-shipping-live.json

# HTML dumps saved to /tmp/idgod-http-probe/
```

## Files saved by probe

- `order.html` — order form source
- `cart.html` — empty cart baseline
- `submit-response.html` — POST response body
- `cart-after-submit.html` — cart with item
