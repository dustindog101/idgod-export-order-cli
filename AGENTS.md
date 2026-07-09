# Agent instructions

## Before you start

1. Read **HANDOFF.md** completely.
2. Work in `/Users/king/Projects/idgod-order-cli`.
3. **Always use a proxy** when hitting idgod.ph — direct curl/Playwright without proxy will fail on this network.
4. Do not commit `proxies/webshare.txt` (contains credentials). Use `proxies/webshare.txt.example`.

## Architecture

- **No REST API** — idgod.ph uses a Django HTML form with multipart POST.
- **Playwright** drives system Chrome with optional HTTP proxy.
- **Parser** normalizes export columns; **orderer** fills `#order-form` and submits.

## Testing protocol

```bash
# 1. Probe
./idgod-order probe --proxy-file proxies/webshare.txt --method both --json

# 2. Dry run (no browser)
./idgod-order order --file <xlsx> --fallback-photo ~/Desktop/good.jpg --dry-run -y

# 3. Single live test
./idgod-order order --file <xlsx> --proxy-file proxies/webshare.txt \
  --fallback-photo ~/Desktop/good.jpg --limit 1 --headed -y --json
```

Success criteria for order command:
- `success: true`
- `cart_count` matches rows submitted
- `total_price` > 0 on `/cart`

## Code conventions

- Match existing style: dataclasses, async Playwright, argparse subcommands (`order`, `probe`).
- Form fields: use `selectors.py` IDs, not fragile label regex.
- Submit via `form.requestSubmit(button)` after destroying Bootstrap validator.
- Keep export-only fields out of `Person` model uploads.

## Do not

- Commit secrets (proxy passwords, real webshare.txt).
- Force-push `main` without user approval.
- Submit real payment without explicit user confirmation.
- Remove proxy requirement — site blocks direct access here.

## GitHub

Repo: `dustindog101/idgod-order-cli`. Push to `main`. See `docs/GITHUB.md`.
