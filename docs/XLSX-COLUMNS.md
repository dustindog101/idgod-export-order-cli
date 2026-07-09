# Spreadsheet column mapping (`orders-*.xlsx`)

Analyzed from `orders-2026-07-08.xlsx` (4 people, 1 shared checkout).

## Per-person fields (each row can differ)

| Column | Maps to | Example row 2 vs 3 |
|--------|---------|---------------------|
| State | ID form state | Washington (same) |
| First / Middle / Last Name | ID names | Anaya… vs Josie Paige Thompson |
| DOB | date of birth | 07/11/2004 vs 09/15/2004 |
| Issue Date | license issue | same batch date |
| Street / City / ZIP | **ID address** (Seattle) | different per person |
| Sex, Height, Weight | physical | different |
| Eye Color, Hair Color | appearance | Brown/Brown vs Green/Blond |
| Photo URL, Signature URL | uploads | unique per row |

## Checkout-only (one address for whole cart)

| Column | Used for |
|--------|----------|
| Shipping | Parsed → cart `#id_name`, `#id_address`, etc. (Oakland, CA) |
| `--email` | Cart email (not in export; pass on CLI) |

## Ignored (export metadata only)

Order ID, Account, Order Date, Status, Payment, Payment Method, Tracking #, Order Note, Export Note, Order Total

## CLI input modes

```bash
# Multi-person file — each row = one ID, shared shipping from Shipping column
./idgod-order order orders.xlsx --checkout --email you@proton.me ...

# Limit rows
./idgod-order order orders.xlsx --limit 2 ...

# Single person via flags (no file)
./idgod-order order --first-name Jane --last-name Doe --state Washington ...

# JSON array of people objects (same field names as columns)
./idgod-order order people.json ...
```

Per-person photos: each row's Photo URL is tried first; `--fallback-photo` only when URL fails.
