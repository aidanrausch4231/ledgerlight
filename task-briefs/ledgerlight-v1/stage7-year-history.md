# Stage 7 — setup syncs the last year of history

GOAL: when the user links an account, ledgerlight requests and imports the last
365 days of transactions, shows import progress, and tells the user when the
full year has arrived.

REPO: personal/ledgerlight (branch `v1-stage7-history`, from main after stage 6 merged)

Read first: `task-briefs/ledgerlight-v1/decisions.md` (binding),
`task-briefs/ledgerlight-v1/stage1-notes.md`, `src/ledgerlight/plaid_client.py`,
`src/ledgerlight/sync.py`, root/component `context.md`, `src/ledgerlight/SKILL.md`.

## Evidence (lead)

`plaid_client.py:67-75` `create_link_token` sends no `transactions.days_requested`,
so Plaid uses its 90-day default. Plaid fixes the history depth at link time; it
cannot be extended for an existing Item without relinking. `sync.py` ignores
`transactions_update_status`, so the app cannot tell when history is complete.

## Build

1. History depth setting `history_days` (settings key + env
   `LEDGERLIGHT_HISTORY_DAYS`, default 365, valid 30–730; invalid → clear error).
   `create_link_token` passes `transactions={"days_requested": history_days}`
   (plaid-python `LinkTokenTransactions`); `sandbox_public_token` passes the same
   via `SandboxPublicTokenCreateRequestOptions(transactions=...)`.
2. Initial import: after token exchange, run sync pages until `has_more` is false
   and record each Item's `transactions_update_status` (store on the item row via
   idempotent migration: `history_status`, `history_days`, `oldest_txn_date`).
   Statuses: `NOT_READY`, `INITIAL_UPDATE_COMPLETE`, `HISTORICAL_UPDATE_COMPLETE`.
   Until historical is complete, the server re-syncs that Item in the background
   every 60 s (bounded: stop after 30 min, and on server shutdown); webhooks are
   out of scope. CLI: `ledgerlight --json sync --wait-history [--timeout 600]`
   blocks until complete or timeout and returns per-item status.
3. UI: Accounts/link flow shows "Importing your last 12 months…" with the
   transaction count and oldest date so far, live (existing SSE/ui_events or
   polling `GET /api/sync/status`), then "Full year imported". Items linked with
   fewer days than `history_days` show "Linked with N days of history — relink to
   fetch a full year" with a Relink button (Plaid update mode is NOT required:
   remove + link again is fine; keep existing user notes/tags by transaction id
   where Plaid ids match).
4. Fake Plaid: generates 365 days of synthetic history, returns
   `INITIAL_UPDATE_COMPLETE` first (30 days) then `HISTORICAL_UPDATE_COMPLETE`
   on a later sync, so the progression is testable offline.
5. Tests: pytest asserts the link-token and sandbox requests carry
   `days_requested=365` (and a custom value), validation bounds, status
   progression, background re-sync stops when complete/time-bound, CLI
   `--wait-history`. Playwright: link via fake, progress text appears, then
   "Full year imported", Transactions page shows dates ~12 months back. The
   lead-run live Sandbox test (`LEDGERLIGHT_E2E_PLAID=sandbox`) additionally
   waits for `HISTORICAL_UPDATE_COMPLETE` and reports the oldest date.
6. Chat bug (lead, live local model): after `show_answer` succeeds, the chat
   keeps showing "Working…" for 3+ minutes while a continuation `/api/agent`
   run streams. Make `show_answer` (and other display-only frontend tools) end
   the turn without a continuation run unless the model asked for more tools,
   and add a 90 s client timeout that clears "Working…" with a retry hint.
   Playwright: after the coffee answer appears, "Working…" is gone within 5 s
   (fake provider).
7. Docs: README setup ("first link imports the last 12 months; big banks may take
   a few minutes"), SKILL.md, context.md.

## OUT OF SCOPE

Webhooks, Plaid update mode, OAuth redirect setup, production keys, `.github/`,
`.env*`, `web/public/`, binary files.

## DONE WHEN

`bash scripts/check.sh` exits 0 from the repo root.
