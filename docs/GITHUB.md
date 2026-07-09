# GitHub setup

## Repository

| | |
|---|---|
| **URL** | https://github.com/dustindog101/idgod-order-cli |
| **Account** | `dustindog101` |
| **Default branch** | `main` |

`gh` is authenticated on this machine (keyring token with `repo` scope).

## Clone

```bash
git clone https://github.com/dustindog101/idgod-order-cli.git
cd idgod-order-cli
python3 -m venv .venv
.venv/bin/pip install -e .
```

## Create repo (already done)

If recreating from scratch:

```bash
cd /Users/king/Projects/idgod-order-cli
gh repo create idgod-order-cli --private --source=. --remote=origin --push
```

Use `--public` only after removing proxy credentials from history.

## Daily workflow

```bash
git checkout -b feature/my-change
# ... edit ...
git add -A
git commit -m "Describe why, not just what"
git push -u origin HEAD
gh pr create --title "..." --body "..."
```

## Secrets

Never commit:
- `proxies/webshare.txt` (real credentials)
- `.env` with tokens

Copy `proxies/webshare.txt.example` → `proxies/webshare.txt` and fill in Webshare creds locally.
