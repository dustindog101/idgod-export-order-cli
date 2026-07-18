# Agent instructions

## Before you start

1. Read **[HANDOFF.md](HANDOFF.md)** completely.
2. Skim **[docs/DOCUMENTATION.md](docs/DOCUMENTATION.md)** for the doc map.
3. Work in `/Users/king/Projects/idgod-order-cli`.
4. **Always use Tor or proxy** for idgod.ph — direct access fails on this network.
5. Do not commit `proxies/webshare.txt` (credentials). Use `proxies/webshare.txt.example`.

## Architecture (2026-07)

- **HTTP (default):** `http_submit.py` — multipart POST, django forms, captcha OCR, BTCPay redirect follow.
- **Playwright:** `orderer.py` — `--browser` / `--playwright` when HTTP captcha fails or debugging UI.
- **Shared:** `IdGodOrderer`, `parser.py`, `cache.py`, `btcpay.py`, `captcha.py`.
- **No public REST API** on idgod.ph — HTML forms only.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Next feature

**Invoice / payment tracking** — [docs/INVOICE-TRACKING.md](docs/INVOICE-TRACKING.md)

User wants to mark orders paid and upload payment receipts after manual BTCPay payment. Start with `cache.py` extensions + `orders` CLI subcommands.

## Testing protocol

```bash
# Unit tests (no network)
pip install -e '.[dev]'
pytest tests/ -q

# Dry run
./idgod-order order <xlsx> --dry-run -y

# Connectivity
./idgod-order probe --tor --method httpx --json

# Single live test — ONLY with user approval
./idgod-order order <xlsx> --tor -e <email> -y --limit 1 --json
```

### Success criteria for live `order`

- `success: true`
- `checkout_completed: true`
- `submitted_ids` matches row count
- `payment_url` is BTCPay
- `discount_applied` matches invoice (if coupon used): 4 IDs ≈ $260 with `hartlr`, not $500

## Code conventions

- Dataclasses for models; async for I/O.
- Form fields: `selectors.py` / `http_forms.py` — not fragile label regex.
- Coupon: always verify via `finalize_coupon_result()` and BTCPay fiat.
- HTTP captcha: pin `captcha_0` to OCR'd image hash; no cart UPDATE in captcha loop.
- Keep export-only metadata out of uploads.

## Git commits

Use the repo owner's GitHub identity (do not use Cursor default):

```bash
git -c user.name='mufasa dev' \
    -c user.email='56493866+dustindog101@users.noreply.github.com' \
    commit -m "…"
```

Never `git config --global`. Never force-push `main` without approval.

## Do not

- Touch **`dustindog101/idgod-order-cli`** — different repo ([docs/REPO-NOT-OTHER.md](docs/REPO-NOT-OTHER.md)).
- Commit secrets, proxy passwords, or receipt uploads.
- Place real orders or spam test checkouts without explicit user confirmation.
- Revert invoice-based coupon logic to “field saved = applied”.
- Remove Tor/proxy requirement documentation.

## GitHub

| | |
|---|---|
| **This repo** | `dustindog101/idgod-export-order-cli` |
| **NOT this** | `dustindog101/idgod-order-cli` |

See [docs/GITHUB.md](docs/GITHUB.md).
