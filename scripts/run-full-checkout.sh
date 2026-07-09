#!/usr/bin/env bash
# Full E2E: spreadsheet → BTCPay invoice. Run in Terminal.app (not Cursor agent).
set -euo pipefail
cd "$(dirname "$0")/.."
PROXY=$(sed -n '1p' proxies/webshare.txt)
exec ./idgod-order order \
  --file ~/Downloads/orders-2026-07-08.xlsx \
  --proxy "$PROXY" \
  --fallback-photo ~/Desktop/good.jpg \
  --fallback-signature ~/Desktop/good.jpg \
  --state-variant "Washington=Washington" \
  --discount hartlr \
  --email test@proton.me \
  -y
