# Handoff checklist for next agent

Copy this prompt to start:

---

You are continuing work on **idgod-order-cli**.

1. Read `/Users/king/Projects/idgod-order-cli/HANDOFF.md` (full context)
2. Read `AGENTS.md` (rules)
3. Clone or open: https://github.com/dustindog101/idgod-order-cli
4. Run setup from `docs/SETUP.md`
5. Copy `proxies/webshare.txt.example` → `proxies/webshare.txt` (ask user for Webshare creds)
6. Run tests from `docs/TESTING.md`
7. Complete P0 tasks in HANDOFF.md (checkout email/shipping, discount workflow)

**Verified working:** 4-person XLSX submit → $480 cart via Seattle proxy.

**Blocked without proxy:** direct idgod.ph access fails on this network.

---

## Files to read (in order)

| # | File | Purpose |
|---|------|---------|
| 1 | HANDOFF.md | Full project context |
| 2 | AGENTS.md | Agent rules |
| 3 | docs/SETUP.md | Install |
| 4 | docs/TESTING.md | Verify it works |
| 5 | docs/KNOWN-ISSUES.md | What's not done |
| 6 | docs/ARCHITECTURE.md | Code map |
| 7 | docs/API-FIELDS.md | Export column mapping |

## Push to GitHub (if needed)

```bash
cd /Users/king/Projects/idgod-order-cli
git remote add origin https://github.com/dustindog101/idgod-order-cli.git
git push -u origin main
```

Account: `dustindog101` — `gh auth status` should show logged in.
