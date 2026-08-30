#!/usr/bin/env bash
# Full E2E: spreadsheet → BTCPay invoice. Run in Terminal.app (not Cursor agent).
set -euo pipefail
cd "$(dirname "$0")/.."
PROXY=$(sed -n '1p' proxies/webshare.txt)
exec ./idgod-order order \
  --file tests/fixtures/synthetic-2-ids.json \
  --tor \
  --fallback-photo tests/fixtures/synthetic_photo.jpg \
  --fallback-signature tests/fixtures/synthetic_signature.jpg \
  --email test@example.com \
  -y
