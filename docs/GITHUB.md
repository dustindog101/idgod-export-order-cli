# GitHub setup

## ⚠️ Not the other repo

**This project:** `dustindog101/idgod-export-order-cli`  
**Do NOT touch:** `dustindog101/idgod-order-cli` (accessibility integration — different project)

See [REPO-NOT-OTHER.md](REPO-NOT-OTHER.md).

## Repository

| | |
|---|---|
| **URL** | https://github.com/dustindog101/idgod-export-order-cli |
| **Account** | `dustindog101` |
| **Default branch** | `main` |

## Clone

```bash
git clone https://github.com/dustindog101/idgod-export-order-cli.git
cd idgod-export-order-cli
python3 -m venv .venv
.venv/bin/pip install -e .
```

## Push (maintainers)

```bash
cd /Users/king/Projects/idgod-order-cli
git remote set-url origin https://github.com/dustindog101/idgod-export-order-cli.git
git push -u origin main
```

Use `gh auth login` or a personal access token — never commit tokens to the repo.

## Daily workflow

```bash
git checkout -b feature/my-change
git add -A && git commit -m "..."
git push -u origin HEAD
gh pr create --title "..." --body "..."
```

## Secrets

Never commit:
- `proxies/webshare.txt` (real credentials)
- `.env` or any `ghp_` tokens

Copy `proxies/webshare.txt.example` → `proxies/webshare.txt` locally.
