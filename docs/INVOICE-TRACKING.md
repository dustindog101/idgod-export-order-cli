# Invoice & payment tracking (planned)

**Status:** Not implemented — spec for the next coding agent.

**User goal:** Place orders via CLI, pay BTCPay invoices manually, then **record which orders were paid** and **upload payment proof** (screenshot, txid, receipt) for bookkeeping.

---

## Current state (what exists today)

### Order placement

`./idgod-order order FILE …` produces a `CheckoutResult` JSON with:

| Field | Example |
|-------|---------|
| `payment_url` | `https://btcpay.idgod.ph/invoice?id=…` |
| `payment_details.invoice_id` | `AXjkREgrthGf1P1Dboqxme` |
| `payment_details.order_number` | `903766` |
| `payment_details.order_status_url` | `https://www.idgod.ph/order/{uuid}` |
| `payment_details.total_fiat` | `$260.00` |
| `payment_details.btc_address` | `bc1q…` |
| `submitted_ids` | List of display names |
| `discount_applied` | `true` when invoice &lt; ~75% of cart |

### Local cache

Every successful run (unless `--no-cache`) saves:

```
~/.cache/idgod-order-cli/orders/YYYYMMDD-HHMMSS-names.json
~/.cache/idgod-order-cli/index.jsonl          # append-only index
```

`OrderCache` lives in `idgod_order_cli/cache.py`. Today it is **write-on-complete + list** only — no payment status, no attachments.

### Invoice lookup

```bash
./idgod-order invoice AXjkREgrthGf1P1Dboqxme
./idgod-order invoice 'https://btcpay.idgod.ph/invoice?id=…'
```

Re-fetches live BTCPay HTML (paid/expired state on vendor side). Does not update local cache.

---

## Proposed data model

Extend each cached order record:

```json
{
  "saved_at": "2026-07-18T04:12:00+00:00",
  "success": true,
  "payment_url": "https://btcpay.idgod.ph/invoice?id=AXjkREgrthGf1P1Dboqxme",
  "payment_details": { "invoice_id": "…", "order_number": "903766", "total_fiat": "$260.00" },
  "submitted_ids": ["Jane Doe", "John Smith"],
  "payment_tracking": {
    "status": "unpaid",
    "marked_paid_at": null,
    "marked_paid_by": null,
    "payment_method": "bitcoin",
    "txid": null,
    "amount_paid_fiat": null,
    "amount_paid_btc": null,
    "notes": "",
    "receipts": []
  }
}
```

### `payment_tracking.status`

| Value | Meaning |
|-------|---------|
| `unpaid` | Default after successful checkout |
| `paid` | User confirmed payment |
| `expired` | BTCPay invoice expired (optional auto-detect via `invoice` command) |
| `cancelled` | Order voided / not proceeding |

### `payment_tracking.receipts[]`

```json
{
  "id": "rcpt-20260718-001",
  "uploaded_at": "2026-07-18T15:30:00-04:00",
  "filename": "btcpay-paid-screenshot.png",
  "path": "~/.cache/idgod-order-cli/receipts/903766/btcpay-paid-screenshot.png",
  "sha256": "…",
  "mime": "image/png",
  "kind": "screenshot"
}
```

`kind`: `screenshot` | `pdf` | `txid_text` | `other`

Store files under:

```
~/.cache/idgod-order-cli/receipts/{order_number or invoice_id}/
```

Never commit receipts to git.

---

## Proposed CLI

### Mark paid

```bash
# By cache file path
./idgod-order orders mark-paid ~/.cache/idgod-order-cli/orders/20260718-041200-anaya.json \
  --txid abc123… \
  --notes "paid from wallet X"

# By invoice id (search index.jsonl)
./idgod-order orders mark-paid --invoice AXjkREgrthGf1P1Dboqxme

# By vendor order number
./idgod-order orders mark-paid --order-number 903766
```

### Upload receipt

```bash
./idgod-order orders upload-receipt --order-number 903766 \
  ~/Desktop/btcpay-confirmation.png \
  --kind screenshot
```

Multiple uploads allowed per order.

### List / filter

```bash
./idgod-order orders list
./idgod-order orders list --unpaid
./idgod-order orders list --paid --json
./idgod-order orders show 903766
```

Consider aliasing `cache list` → `orders list` for backward compatibility.

### Optional: sync status from BTCPay

```bash
./idgod-order orders refresh --invoice AXjkREgrthGf1P1Dboqxme
```

Parse BTCPay page for “Paid” / “Expired” and update `payment_tracking.status` without user upload.

---

## Implementation notes

### Files to touch

| File | Change |
|------|--------|
| `idgod_order_cli/cache.py` | `load()`, `update()`, `find_by_invoice()`, receipt storage |
| `idgod_order_cli/models.py` | `PaymentTracking`, `Receipt` dataclasses |
| `idgod_order_cli/cli.py` | `orders` subcommand group |
| `tests/test_cache.py` | mark-paid, upload, find |
| `docs/GUIDE.md` | User-facing section |

### Index updates

When marking paid, append to `index.jsonl` or maintain a small SQLite DB. JSONL is fine for &lt;1000 orders; migrate to SQLite if search gets slow.

### Admin web UI (optional P1)

If CLI uploads are awkward:

- Local-only FastAPI on `127.0.0.1:8765`
- Table: unpaid orders from cache
- Drag-drop receipt → calls same `OrderCache.upload_receipt()`
- No auth in v1 (localhost only); add token if exposed

### Security

- Receipts may contain wallet info — keep under `~/.cache/`, chmod 700
- Do not log txids or paths in verbose mode by default
- `.gitignore` already should exclude `receipts/`

---

## Acceptance criteria

1. After `order` succeeds, `orders list --unpaid` shows the new invoice.
2. `mark-paid --order-number N` sets status and timestamp; idempotent.
3. `upload-receipt` stores file and adds entry to `receipts[]`.
4. `orders show N` prints human summary: names, fiat, BTC, status, receipt paths.
5. Unit tests cover cache load/update/find without network.
6. Docs updated in GUIDE.md and HANDOFF.md.

---

## Related commands today

```bash
# Place order (creates cache entry)
./idgod-order order orders.xlsx --tor -e you@email.com -y

# Look up vendor invoice (does not update cache)
./idgod-order invoice <id>

# List past runs (no payment status yet)
./idgod-order cache list
```
