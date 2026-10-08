# Stage 3 correction (builder)

Fix exactly these two reviewer findings on branch `v1-stage3-ui`, then run
`bash scripts/check.sh` until it exits 0. Do not change anything else. Never use
git stash, never commit. Never touch `.env*`, `task-briefs/`, `design/`, `web/public/`.

1. `web/src/lib/uiBus.ts:78` clears the Undo receipt for every `dashboard.undo`
   event. Only clear it for user-originated undo. For `agent`/`cli` undo events,
   show an Undo receipt like other non-user changes (undoing an undo restores
   the layout via `dashboardCommand('undo', { expected_version: dashboard.version }, 'user')`
   or the existing equivalent). Add a Playwright assertion in
   `web/e2e/dashboard.spec.ts`: run CLI `dashboard undo` while the page is open,
   the layout changes live and a receipt appears; clicking it reverses.
2. `src/ledgerlight/dashboard.py:288-291`: undo replaces every card's
   `updated_at`. When `action == "undo"`, restore the stored prior snapshot
   exactly (all fields, including timestamps); only ordinary mutations update
   timestamps. Add a pytest asserting full card equality (including timestamps)
   between the restored layout and the prior stored version.

Reply: STATUS / FILES (path:line) / CHECKS (command + result).
