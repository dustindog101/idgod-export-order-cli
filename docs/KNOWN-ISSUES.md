# Known issues & gaps

## Environment

| Issue | Impact | Workaround |
|-------|--------|------------|
| Direct IP blocked by idgod.ph | Cannot reach site without proxy | `--proxy` or `--tor` required |
| Playwright bundled Chromium x64 on arm64 | SIGSEGV on launch | Auto-fallback to `channel="chrome"` |
| Low disk space (~98% full) | Browser crashes | Free cache before long runs |

## Feature gaps

### Discount code `hartlr`
- **Status:** Not auto-applied
- **Reason:** No coupon input on `/order` or `/cart` HTML
- **Workaround:** Email idgod@idgod.ph after placing order

### Shipping / email checkout
- **Status:** Not implemented
- Export `Shipping` column is parsed but not used
- Cart page asks for email + delivery address — manual step

### Per-person photos
- **Status:** Single `--fallback-photo` used for all rows when URLs dead
- **TODO:** Resolve each row's Photo URL / path independently

### Payment
- Site emails payment instructions; no instant Stripe URL
- CLI captures `/cart` URL and on-page payment method list only

### Session persistence
- Each CLI run = new browser session
- Cart from previous run is lost unless cookies saved

## Form quirks

- Bootstrap `data-toggle="validator"` blocks naive button clicks
- Fixed via `validator('destroy')` + `form.requestSubmit(btn)`
- `date_of_birth` uses bootstrap-datepicker class
- Height/weight inputs are `type="number"`

## Proxy credentials

Webshare free proxies expire/rotate. Update `proxies/webshare.txt` when probe fails.

Do not commit real credentials to public GitHub.
