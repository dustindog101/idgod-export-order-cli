# Testing

## Probe (no order placed)

```bash
./idgod-order probe --proxy-file proxies/webshare.txt --method both --json
```

Expected: at least one result with `"ok": true`, `"form_fields": 19`.

## Dry run (parse only)

```bash
./idgod-order order \
  --file /Users/king/Downloads/orders-2026-07-08.xlsx \
  --fallback-photo /Users/king/Desktop/good.jpg \
  --dry-run -y --json
```

Expected: `"success": true`, `"dry_run": true`, 4 people listed.

## Dry run with checkout parsing

```bash
./idgod-order order \
  --file /Users/king/Downloads/orders-2026-07-08.xlsx \
  --fallback-photo /Users/king/Desktop/good.jpg \
  --checkout --email test@example.com \
  --dry-run -y --json
```

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
