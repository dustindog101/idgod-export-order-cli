# Handoff checklist for next agent

Copy this prompt to start:

---

You are continuing work on **idgod-order-cli** (IDGod order automation CLI).

1. Read `/Users/king/Projects/idgod-order-cli/HANDOFF.md` (full context)
2. Read `AGENTS.md` (rules)
3. Read `docs/DOCUMENTATION.md` (doc index)
4. **Next feature:** `docs/INVOICE-TRACKING.md` — mark orders paid, upload payment receipts
5. Repo: https://github.com/dustindog101/idgod-export-order-cli  
   **NOT** https://github.com/dustindog101/idgod-order-cli
6. Run `pytest tests/ -q` before and after changes
7. Do **not** place live test orders without explicit user approval (vendor bans spam)

**Verified (2026-07-18):** HTTP 4-ID order, export photos only, `hartlr` → $260 BTCPay invoice.

**Transport:** HTTP default; `--playwright` fallback.

---

## Files to read (in order)

| # | File | Purpose |
|---|------|---------|
| 1 | HANDOFF.md | Project context & status |
| 2 | AGENTS.md | Agent rules |
| 3 | docs/INVOICE-TRACKING.md | **Implement this next** |
| 4 | docs/ROADMAP.md | Priorities |
| 5 | docs/GUIDE.md | CLI reference |
| 6 | docs/ARCHITECTURE.md | Code map |
| 7 | docs/TESTING.md | Verify locally |

## Git commits

Use owner identity (not Cursor default):

```bash
git -c user.name='mufasa dev' \
    -c user.email='56493866+dustindog101@users.noreply.github.com' \
    commit -m "your message"
```

## Push

```bash
cd /Users/king/Projects/idgod-order-cli
git push -u origin feat/http-orderer   # or main when merging
```

Account: `dustindog101` — `gh auth status` should show logged in.
