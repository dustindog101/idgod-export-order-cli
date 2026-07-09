# Known issues & gaps

## Environment

| Issue | Impact | Workaround |
|-------|--------|------------|
| Direct IP blocked by idgod.ph | Cannot reach site without proxy | `--proxy` or `--tor` required |
| Playwright bundled Chromium x64 on arm64 | SIGSEGV on launch | Auto-fallback to `channel="chrome"` |
| Low disk space | Browser crashes | Free cache before long runs |

## Feature gaps

### FINISH ORDER / captcha
- **Status:** Not automatable headlessly
- Cart page has `#id_captcha_1` — blocks `--checkout-submit`
- **Workaround:** Run `--checkout --headed`, solve captcha, click FINISH ORDER manually

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
