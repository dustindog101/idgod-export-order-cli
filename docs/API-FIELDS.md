# Field mapping

## Export → idgod.ph form

| Export column | Form field | ID | Required |
|---------------|------------|-----|----------|
| First Name | first_name | `#id_first_name` | Yes |
| Middle Name | middle_name | `#id_middle_name` | No |
| Last Name | last_name | `#id_last_name` | Yes |
| DOB | date_of_birth | `#id_date_of_birth` | Yes (MM/DD/YYYY) |
| State | state | `#id_state` | Yes (dropdown) |
| Height | height_feet + height_inches | `#id_height_feet`, `#id_height_inches` | Yes (parsed from `5'4"`) |
| Weight | weight | `#id_weight` | Yes (number) |
| Eye Color | eyes | `#id_eyes` | Yes |
| Hair Color | hair | `#id_hair` | Yes |
| Sex | gender | `#id_gender` | Yes |
| Street | address1 | `#id_address1` | No (on-ID address) |
| City | city | `#id_city` | Yes |
| ZIP | zip | `#id_zip` | Yes |
| Photo URL | picture | `#id_picture` | Yes (file upload) |
| Signature URL | signature | `#id_signature` | No |
| Issue Date | custom_license_number | `#id_custom_license_number` | No (+$20) |

## Never sent to idgod.ph

| Export column | Reason |
|---------------|--------|
| Order ID | Internal export metadata |
| Account | Internal |
| Order Date | Internal |
| Status | Internal |
| Payment | Internal |
| Payment Method | Internal |
| Tracking # | Internal |
| Order Note | Internal |
| Export Note | Internal |
| Order Total | Internal pricing |

## Export → checkout

`Shipping` is not sent to the ID form. It is parsed only when `--checkout` is enabled, then used for checkout delivery fields.

| Export column / CLI flag | Checkout value |
|--------------------------|----------------|
| Shipping | `name`, `street`, `city`, `state`, `zip`, `country` |
| Email / `--email` | checkout email |
| `--shipping` | full shipping override |
| `--shipping-name` | recipient name override |
| `--shipping-street` | street override |
| `--shipping-city` | city override |
| `--shipping-state` | state override |
| `--shipping-zip` | zip override |
| `--shipping-country` | country override |

## Shipping column format (from sample)

```
Anaya Samsotha-Cooley, 5125 Leona St, Oakland, CA, 94619, USA
```

This now parses automatically with `--checkout` and can be verified without a browser:

```bash
./idgod-order order --file /Users/king/Downloads/orders-2026-07-08.xlsx \
  --fallback-photo /Users/king/Desktop/good.jpg \
  --checkout --email test@example.com --dry-run -y --json
```

## State dropdown

Washington export maps to single option: `Washington` ($100 base, cart showed $120/ID with quantity pricing).

Other states may have many variants (Polycarbonate, CDL, etc.). Use:
- `--state-variant "California=California"`
- `--cheapest-state`

## Eye/hair value mapping

See `states.py` — normalizes `Blond` → `Blonde`, etc.
