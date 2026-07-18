# Known issues & gaps

## Environment

| Issue | Impact | Workaround |
|-------|--------|------------|
| Direct IP blocked by idgod.ph | Cannot reach site without proxy | `--tor` or `--proxy` required |
| Playwright bundled Chromium x64 on arm64 | SIGSEGV on launch | Auto-fallback to `channel="chrome"` |
| Vendor rate-limits test orders | Coupon/IP ban | Ask user before bulk live runs |

## Resolved (2026-07)

| Item | Status |
|------|--------|
| HTTP transport as default | ✅ |
| Full checkout + captcha + BTCPay | ✅ HTTP and Playwright |
| Coupon `hartlr` on invoice | ✅ `finalize_coupon_result()` |
| HTTP captcha always rejected | ✅ Fixed hash rotation (no UPDATE in captcha loop) |
| Per-person export photos | ✅ Prefetch URLs direct, upload via Tor |
| Cart checkout fields | ✅ |
| Shipping from export column | ✅ |
| `idgod-order invoice` lookup | ✅ |

## Open gaps

### Payment tracking (P0 — planned)

- No way to mark an order **paid** or attach payment proof yet
- Spec: [INVOICE-TRACKING.md](INVOICE-TRACKING.md)

### HTTP captcha OCR accuracy

- Sometimes fails 15/15; Playwright often succeeds on same site
- Try `--playwright` or `--captcha-solver 2captcha`
- Debug PNGs: `~/.cache/idgod-order-cli/captcha-debug/`

### Session persistence

- Each run = new session; cart not preserved between CLI invocations

### Coupon vendor-side

- Code can be disabled by vendor for excessive test orders
- `--no-require-coupon` allows full-price checkout if code inactive

## Form quirks

- Order address (`#id_address1`) ≠ shipping address (`#id_address` on cart)
- Cart: click UPDATE after filling fields before FINISH
- Order form: Bootstrap validator — Playwright uses `requestSubmit` after `validator('destroy')`
- **HTTP captcha:** never POST `action=update` between reading captcha image and `action=finish`

## Feature flags reference

| Flag | Effect |
|------|--------|
| `--discount ""` | No coupon |
| `--no-require-coupon` | Coupon optional at checkout |
| `--no-cache` | Skip saving result JSON |
| `--no-fetch-payment` | Skip BTCPay scrape |
| `--playwright` | Browser instead of HTTP |
