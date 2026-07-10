# Spreadsheet / JSON export mapping

Supports the **vendor-safe export** (`EXPORT-SPEC.md`): nested JSON `orders[].ids[]` and flat XLSX `Orders` sheet (25 columns). Legacy CSV/flat JSON still work.

## Per-person fields (each row / id object)

Maps to the ID order form. If idgod lists multiple dropdown options for a state, the CLI **picks the cheapest match by default** (override with `--state-variant`).

| Column | Maps to | Example row 2 vs 3 |
|--------|---------|---------------------|
| State | ID form state | Washington (same) |
| First / Middle / Last Name | ID names | Anaya… vs Josie Paige Thompson |
| DOB | date of birth | 07/11/2004 vs 09/15/2004 |
| Issue Date | license issue | same batch date |
| Street / City / ZIP | **ID address** (Seattle) | different per person |
| Sex, Height, Weight | physical | different |
| Eye Color, Hair Color | appearance | Brown/Brown vs Green/Blond |
| Photo URL / `photoUrl` | uploads | unique per row |
| Signature URL / `signatureUrl` | uploads | unique per row |
| Product ID / `productId` | state dropdown variant | e.g. `Washington`, `CA:DMV_POLY` → polycarbonate |

Vendor template columns (`PHOTO LINK`, `STREET ADDRESS`, `ZIP CODE`, …) still map via aliases.

## Checkout (from export, not CLI flags)

| Source | Used for |
|--------|----------|
| `Shipping Address` / `shippingAddress` | Cart name, street, city, state, zip |
| JSON `shippingOverride` (non-null) | Same address for every order in file |
| `--email` | Cart email (required for checkout) |
| `Local Delivery` | Pickup — CLI fills email/payment only; use `--shipping` to override |

## Ignored metadata

Order ID, Status, Tracking #, Order Note, Export Note, ID #, Account, etc.

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
