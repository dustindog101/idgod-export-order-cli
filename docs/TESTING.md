# Testing

## Unit tests (no network)

```bash
pip install -e '.[dev]'
pytest tests/ -q
```

Covers: parser, captcha helpers, HTTP forms/coupon logic, order cache, BTCPay HTML parsing, proxy/Tor manager.

## Dry run (parse only)

```bash
./idgod-order order tests/fixtures/synthetic-2-ids.json --dry-run -y
```

Expected: `success: true`, synthetic IDs listed, no network.

## Connectivity probe

```bash
./idgod-order probe --tor --method httpx --json
```

## Live order (user approval required)

```bash
./idgod-order order tests/fixtures/synthetic-1-id.json \
  --tor \
  -e test@example.com \
  --fallback-photo tests/fixtures/synthetic_photo.jpg \
  --fallback-signature tests/fixtures/synthetic_signature.jpg \
  -y --json --single-checkout
```

Expected:

| Field | Value |
|-------|-------|
| `success` | `true` |
| `checkout_completed` | `true` |
| `submitted_ids` | List of submitted names |
| `payment_url` | `https://btcpay.idgod.ph/invoice?id=…` |
| `transport` | `http` |

Omit `--fallback-photo` when export image URLs are verified live.

## Playwright fallback test

```bash
./idgod-order order tests/fixtures/synthetic-1-id.json \
  --tor \
  -e test@example.com \
  --fallback-photo tests/fixtures/synthetic_photo.jpg \
  --fallback-signature tests/fixtures/synthetic_signature.jpg \
  --playwright -y
```

Same success criteria; `transport: browser`.

## Invoice lookup

```bash
./idgod-order invoice <invoice_id> --json
```

## Cache list

```bash
./idgod-order cache list
```

## Verify export images before order

```bash
uv run python scripts/verify-vendor-images.py tests/fixtures/synthetic-2-ids.json
```

## Coupon manual probe (dev)

```bash
uv run python scripts/coupon-manual-probe.py tests/fixtures/synthetic-1-id.json --checkout
```
