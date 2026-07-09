# Setup

## Requirements

- macOS (tested on arm64)
- Python 3.10+
- Google Chrome installed (Playwright uses `channel="chrome"` fallback)
- Network proxy or Tor (direct idgod.ph access blocked on dev machine)

## Install

```bash
cd /Users/king/Projects/idgod-order-cli   # or clone from GitHub
python3 -m venv .venv
.venv/bin/pip install -e .
```

Optional Tor support:
```bash
brew install tor          # system Tor binary
# OR embedded via pip dependency torpy (already in pyproject.toml)
```

## Proxies

```bash
cp proxies/webshare.txt.example proxies/webshare.txt
# Edit with host:port:user:pass per line
```

Test:
```bash
./idgod-order probe --proxy-file proxies/webshare.txt --json
```

## Wrapper script

```bash
chmod +x idgod-order
./idgod-order --help
```

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `connection reset by peer` | Add `--proxy` or `--tor` |
| Playwright Chromium SIGSEGV | Uses Chrome fallback automatically; ensure Chrome installed |
| `externally-managed-environment` | Use `.venv`, not system pip |
| Cart total $0.00 | Form didn't POST — check validator bypass in orderer.py |
| Photo upload fails | Use `--fallback-photo` with local JPG |
