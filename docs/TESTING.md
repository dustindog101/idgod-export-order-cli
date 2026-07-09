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

1. Cart page email + shipping fields (inspect with `--headed`)
2. Payment method selection + final submit
3. Per-row photo URLs when valid
4. States with multiple dropdown options
