"""Help text for CLI — concise on-screen; see docs/GUIDE.md for full detail."""

from __future__ import annotations

ORDER_DESCRIPTION = """\
Place complete orders from a spreadsheet export (HTTP by default — fast, no browser).

  Row data     → each person's ID form (name, DOB, address, photo, …)
  Shipping col → one shared delivery address at checkout
  --email      → where payment instructions are sent

A real run does everything: ID forms → cart → coupon → captcha → BTCPay invoice.
HTTP is default; add --browser or --playwright for Chrome automation."""

ORDER_EPILOG = """\
examples:
  # Fast HTTP (default)
  idgod-order order orders.xlsx --tor -e you@example.com \\
    --fallback-photo ~/Desktop/good.jpg

  # Playwright / Chrome (same flags + --browser or --playwright)
  idgod-order order orders.xlsx --tor -e you@example.com --browser
  idgod-order order orders.xlsx --tor -e you@example.com --playwright --headed

  idgod-order order orders.xlsx --proxy-file proxies/webshare.txt \\
    --email you@example.com --fallback-photo ~/Desktop/good.jpg --limit 1

  idgod-order order orders.xlsx --dry-run
  idgod-order probe --tor
  idgod-order cache list
  idgod-order invoice 8oDSQNud6WzNy4ASS9ZMEY --tor

payment (--payment-method, default: bitcoin):
  bitcoin    Bitcoin on BTCPay
  litecoin   Litecoin
  card       Credit/debit, Apple Pay, Google Pay

shipping (--shipping-method, default: standard):
  standard   ~20 business days, $20
  express    ~10–14 days, $50
  super      ~5–8 days, $120 (≤10 people)

state ID type (when a state has multiple dropdown options):
  default    picks the cheapest matching option automatically
  override   --state-variant "Washington=Washington Polycarbonate"

more: docs/GUIDE.md
"""

PAYMENT_CHOICES = ("bitcoin", "litecoin", "card")
SHIPPING_CHOICES = ("standard", "express", "super", "group")

PAYMENT_HELP = "bitcoin (default), litecoin, card"
SHIPPING_HELP = "standard $20 (default), express $50, super $120, group $200"

ROOT_DESCRIPTION = "Submit IDGod orders from CSV/XLSX/JSON exports."
