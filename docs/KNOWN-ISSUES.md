# Known issues & gaps

## Environment

| Issue | Impact | Workaround |
|-------|--------|------------|
| Direct IP blocked by idgod.ph | Cannot reach site without proxy | `--proxy` or `--tor` required |
| Playwright bundled Chromium x64 on arm64 | SIGSEGV on launch | Auto-fallback to `channel="chrome"` |
| Low disk space | Browser crashes | Free cache before long runs |

## Feature gaps

### FINISH ORDER / captcha
- Cart uses django-simple-captcha (`#id_captcha_1` + image)
- **Automated:** `--checkout-submit` with `--captcha-solver ppllocr` (install `pip install -e '.[captcha]'`) or `--captcha-solver 2captcha` + `TWOCAPTCHA_API_KEY`
- **Manual:** `--captcha-solver manual --headed`
- **Disk:** ppllocr wheel is ~67MB; use 2captcha if disk is tight

### Discount code
- **Status:** ✅ Fills `#id_coupon` and clicks UPDATE when `--checkout`
- Verify total actually drops after UPDATE (may depend on code validity)

### Per-person photos
- Each row's Photo URL is tried first; `--fallback-photo` only when URL fails
- Dead URLs in export all use same fallback image

### Session persistence
- Each CLI run = new browser session; cart not preserved between runs

## Resolved (2026-07-09)

- ✅ Cart checkout fields (name, address, email, payment, shipping)
- ✅ Coupon field on cart page
- ✅ Shipping parsed from export `Shipping` column
- ✅ Default payment Bitcoin when `--checkout`
- ✅ Default shipping standard $20

## Form quirks

- Order form: Bootstrap validator — use `requestSubmit` after `validator('destroy')`
- Cart form: must click UPDATE after filling fields
- Order address (`#id_address1`) ≠ shipping address (`#id_address` on cart)
