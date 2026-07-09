# Architecture

## Flow

```
Export file (XLSX/CSV/JSON)
        │
        ▼
   parser.py ──► list[Person]
        │
        ▼
   proxies.py ──► pick working proxy / start Tor
        │
        ▼
   orderer.py ──► Playwright + Chrome
        │              │
        │              ├─ GET /order (via proxy)
        │              ├─ Fill #order-form fields
        │              ├─ POST multipart (action=1 continue, action=2 checkout)
        │              └─ GET /cart → read #total
        │
        ▼
   CheckoutResult (JSON)
```

## Modules

### `cli.py`
- Subcommands: `order`, `probe`
- Backward compat: `idgod-order file.xlsx` → `order file.xlsx`
- Collects proxy flags, loads people, prints JSON or human output

### `parser.py`
- Maps export headers via `FIELD_ALIASES`
- Skips `EXPORT_ONLY_FIELDS`
- Supports CLI single-person flags

### `orderer.py`
- `IdGodOrderer.submit()` orchestrates browser session
- `_fill_person()` per row; last row uses checkout button (action=2)
- Destroys jQuery Bootstrap validator before `requestSubmit`
- `_apply_discount()` — best-effort; usually no field found

### `proxies.py`
- `parse_proxy_line()` — `host:port:user:pass` or URL form
- `TorManager` — existing Tor :9050 → spawn `tor` binary → torpy embedded
- `test_proxy_playwright()` / `pick_working_proxy()` for failover

### `selectors.py`
- Django auto-generated IDs: `#id_first_name`, `#id_weight`, etc.

### `states.py`
- `pick_state_option()` — exact/prefix match, cheapest, or error on ambiguity

## External dependencies

| Package | Purpose |
|---------|---------|
| playwright | Browser automation |
| httpx | Image download, proxy probe |
| openpyxl | XLSX parsing |
| torpy | Embedded Tor SOCKS (optional) |

## idgod.ph technical notes

- Django CSRF: `csrfmiddlewaretoken` in form (handled by browser session)
- Form: `enctype="multipart/form-data"`, `method="post"`
- Cart total element: `#total`
- Washington has single dropdown option (no polycarbonate variant)
