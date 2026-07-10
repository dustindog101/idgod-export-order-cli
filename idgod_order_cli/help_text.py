"""Help text for CLI — concise on-screen; see docs/GUIDE.md for full detail."""

from __future__ import annotations

ORDER_DESCRIPTION = """\
Submit orders from an export file (.xlsx, .csv, or .json).

Each row → one ID on idgod.ph. Shipping comes from the export (or --shipping).
A real run fills forms, applies coupon, solves captcha, and returns the BTCPay invoice."""

ORDER_EPILOG = """\
quick start (order is optional when the first argument is a file):

  idgod-order orders.xlsx --email you@proton.me --tor
  idgod-order orders.xlsx --dry-run
  idgod-order run orders.xlsx -e you@proton.me --tor    # same as order

other commands:
  idgod-order check --tor              test connection (alias: probe)
  idgod-order invoice INVOICE_ID --tor   look up payment / order #
  idgod-order cache                      past results (alias: cache list)

environment:
  IDGOD_EMAIL   default for --email

payment (--payment-method):  bitcoin (default), litecoin, card
shipping (--shipping-method): standard $20 (default), express, super, group

more: docs/GUIDE.md
"""

PAYMENT_CHOICES = ("bitcoin", "litecoin", "card")
SHIPPING_CHOICES = ("standard", "express", "super", "group")

PAYMENT_HELP = "bitcoin (default), litecoin, card"
SHIPPING_HELP = "standard $20 (default), express $50, super $120, group $200"

ROOT_DESCRIPTION = """\
Submit IDGod orders from spreadsheet exports.

Most common:
  idgod-order FILE --email you@proton.me --tor"""

ROOT_EPILOG = ORDER_EPILOG
