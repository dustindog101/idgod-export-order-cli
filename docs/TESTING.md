# Testing

## Unit tests (no network)

```bash
pip install -e '.[dev]'
pytest tests/ -q
```

Covers: parser, captcha helpers, HTTP forms/coupon logic, order cache, BTCPay HTML parsing, proxy/Tor manager.

## Dry run (parse only)

```bash
./idgod-order order ~/Downloads/orders-2026-07-18.xlsx --dry-run -y
```

Expected: `success: true`, 4 people listed, no network.

## Connectivity probe

```bash
./idgod-order probe --tor --method httpx --json
```

## Live order (user approval required)

```bash
./idgod-order order ~/Downloads/orders-2026-07-18.xlsx \
  --tor \
  -e contact@mail.idpirate.com \
  -y --json --single-checkout \
  --discount hartlr
```

Expected:

| Field | Value |
|-------|-------|
| `success` | `true` |
| `checkout_completed` | `true` |
| `submitted_ids` | 4 names |
| `payment_url` | `https://btcpay.idgod.ph/invoice?id=…` |
| `discount_applied` | `true` (4 IDs → ~$260 invoice) |
| `transport` | `http` |

Omit `--fallback-photo` when export image URLs are verified live.

## Playwright fallback test

```bash
./idgod-order order … --playwright …
```

Same success criteria; `transport: browser`.

## Invoice lookup

```bash
./idgod-order invoice AXjkREgrthGf1P1Dboqxme --json
```

## Cache list

```bash
./idgod-order cache list
```

## Verify export images before order

```bash
uv run python scripts/verify-vendor-images.py ~/Downloads/orders-2026-07-18.xlsx
```

## Coupon manual probe (dev)

```bash
uv run python scripts/coupon-manual-probe.py orders.xlsx --checkout
```

---

## Legacy notes

Older docs referenced `--checkout` as a separate flag. As of 2026-07, `order` runs full checkout by default. Use `--dry-run` to skip network.

Expected:
- `"success": true`
- `"checkout_attempted": true`
- `"checkout_completed": false` because dry-run does not launch the browser
- `"shipping"` contains name, street, city, state, zip parsed from the export `Shipping` column

Recorded 2026-07-09 sample shipping:
`Anaya Samsotha-Cooley, 5125 Leona St, Oakland, CA, 94619, USA`

## Single live order

```bash
./idgod-order order \
  --file /Users/king/Downloads/orders-2026-07-08.xlsx \
  --proxy 31.56.127.193:7684:xupznkqu:nn697wqma9r6 \
  --fallback-photo /Users/king/Desktop/good.jpg \
  --fallback-signature /Users/king/Desktop/good.jpg \
  --state-variant "Washington=Washington" \
  --limit 1 --headed -y --json
```

Expected:
- `"success": true`
- `"total_price": 130.0` (approx, may vary)
- `"payment_url": "https://www.idgod.ph/cart"`

## Full batch (verified 2026-07-09)

```bash
./idgod-order order \
  --file /Users/king/Downloads/orders-2026-07-08.xlsx \
  --proxy 31.56.127.193:7684:xupznkqu:nn697wqma9r6 \
  --fallback-photo /Users/king/Desktop/good.jpg \
  --fallback-signature /Users/king/Desktop/good.jpg \
  --state-variant "Washington=Washington" \
  -y --json
```

**Recorded result:**
- 4/4 success
- Total $480.00, $120/ID
- Discount `hartlr` not applied (no UI field)

## Tor test

```bash
./idgod-order probe --tor --method httpx --json
```

May be slow; embedded torpy bootstraps circuit.

## What to test next

1. Cart page email + shipping fields with `--checkout --headed --limit 1`
2. Payment method selection via `--payment-method`, stopping before payment
3. Per-row photo URLs when valid
4. States with multiple dropdown options

## Agent notes

- Use `./idgod-order` or `.venv/bin/python -m idgod_order_cli`; global `python3` may not have dependencies.
- If `py_compile` fails with `Operation not permitted` on `__pycache__`, retry with `PYTHONPYCACHEPREFIX=/tmp/idgod-pyc`.
- Empty `/cart` HTML has no checkout form controls. Use a real non-empty cart/browser session to verify exact checkout selectors.
