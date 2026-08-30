# Cart / checkout form (`/cart`)

Scraped from live cart with items (2026-07-09).

## Fields

| ID | Name | Purpose |
|----|------|---------|
| `#id_name` | name | Recipient full name |
| `#id_phone_number` | phone_number | Optional phone |
| `#id_address` | address | Shipping street |
| `#id_city` | city | Shipping city |
| `#id_state` | state | Shipping state |
| `#id_zip` | zip | Shipping ZIP |
| `#id_country` | country | Country (default USA) |
| `#id_email` | email | Payment instructions sent here |
| `#id_payment_method` | payment_method | Bitcoin / Litecoin / Card |
| `#id_priority` | priority | Shipping speed tier |
| `#id_coupon` | coupon | Optional discount code |
| `#id_captcha_1` | captcha_1 | **Blocks automated FINISH ORDER** |

## Buttons

| Value | Label | Action |
|-------|-------|--------|
| `update` | UPDATE | Save cart fields + coupon |
| `finish` | FINISH ORDER | Submit order (requires captcha) |
| `delete` | REMOVE | Remove cart item |

## Payment method values

| Value | Label |
|-------|-------|
| `0` | Bitcoin |
| `2` | Litecoin |
| `8` | Credit/Debit Cards, Apple Pay & Google Pay |

## Shipping (`#id_priority`) values

| Value | Description |
|-------|-------------|
| `9` | 20 days $20 (default) |
| `6` | Express 10-14 days $50 |
| `7` | Super express 5-8 days $120 (≤10 people) |
| `11` | Super express $200 (10-30 people) |

CLI aliases: `standard`, `express`, `super` — see `selectors.SHIPPING_ALIASES`.

## Automation limits

- CLI fills all fields + coupon and clicks **UPDATE**
- **FINISH ORDER** requires captcha — use `--checkout-submit` with `--captcha-solver ppllocr` or `2captcha`, or `--headed` + manual solve
