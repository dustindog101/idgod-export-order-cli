# Documentation index

Start here, then drill into the topic you need.

## New users

| Doc | What it covers |
|-----|----------------|
| [README.md](../README.md) | Install, one-line quick start |
| [GUIDE.md](GUIDE.md) | Full CLI reference: flags, coupons, captcha, output |
| [SETUP.md](SETUP.md) | venv, dependencies, Tor, proxies |
| [XLSX-COLUMNS.md](XLSX-COLUMNS.md) | Export spreadsheet column mapping |

## Operators

| Doc | What it covers |
|-----|----------------|
| [TESTING.md](TESTING.md) | Dry-run, live tests, what “success” looks like |
| [KNOWN-ISSUES.md](KNOWN-ISSUES.md) | Environment quirks, workarounds |
| [CART-FORM.md](CART-FORM.md) | Cart/checkout field IDs |
| [API-FIELDS.md](API-FIELDS.md) | Per-field mapping to idgod.ph |

## Developers & coding agents

| Doc | What it covers |
|-----|----------------|
| [HANDOFF.md](../HANDOFF.md) | **Read first** — project context, status, commands |
| [AGENTS.md](../AGENTS.md) | Rules for AI agents working in this repo |
| [HANDOFF-PROMPT.md](HANDOFF-PROMPT.md) | Copy-paste prompt to onboard a new agent |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Modules, HTTP vs Playwright, data flow |
| [ROADMAP.md](ROADMAP.md) | Planned features (priority order) |
| [INVOICE-TRACKING.md](INVOICE-TRACKING.md) | **Next big feature** — paid-order tracking spec |
| [GITHUB.md](GITHUB.md) | Clone, push, branch workflow |
| [REPO-NOT-OTHER.md](REPO-NOT-OTHER.md) | Do not confuse with `idgod-order-cli` |

## Scripts (dev helpers)

| Script | Purpose |
|--------|---------|
| `scripts/coupon-manual-probe.py` | Headed cart + optional checkout coupon test |
| `scripts/verify-vendor-images.py` | Check export photo/signature URLs |
| `scripts/http-post-probe.py` | Low-level HTTP form probe |
| `scripts/captcha-probe.py` | OCR a captcha image offline |

## CLI commands (summary)

```bash
./idgod-order order FILE …     # Place order(s) — HTTP by default
./idgod-order probe --tor      # Test connectivity
./idgod-order cache list       # Past run JSON logs
./idgod-order invoice ID       # Look up BTCPay invoice by id or URL
```

See [GUIDE.md](GUIDE.md) for every flag.
