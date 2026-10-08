# Stage 2 notes (lead, 2026-10-03) — what exists now

Merged as the stage 2 PR. `bash scripts/check.sh`: ~101 pytest tests, offline
Playwright `web/e2e/plaid.spec.ts` + `web/e2e/money.spec.ts`.

- `src/ledgerlight/money.py` — all stage 2 shared logic. Every data-changing
  function takes `apply=True` and returns a change summary; with `apply=False`
  it validates and describes without writing (stage 4 `--propose` builds on
  this). Key functions: `rules_*`, `txn_change(id, action, ...)`,
  `spending_summary(month)`, `cashflow(months)`, `budgets_*`,
  `budgets_report(month)`, `recurring_mark`, `bills_upcoming(days)`,
  `settings_get/set`, `alerts_list/dismiss/refresh`, `goals_*`, `today()`
  (honors `LEDGERLIGHT_TODAY`).
- `src/ledgerlight/money_cli.py` / `money_api.py` — thin CLI and API adapters,
  registered from `cli.py` / `api.py`.
- `src/ledgerlight/data.py` — stage 1 read queries (accounts, transactions,
  recurring, networth).
- Web: `web/src/App.tsx` hash router; pages in `web/src/pages/`, shared code in
  `web/src/lib/`, components in `web/src/components/`. Plain CSS in
  `web/src/index.css` (stage 3 replaces styling with the chosen design tokens).
- Sign convention: negative = outflow. Hidden and pending rows are excluded
  from budgets/spending/cash flow; splits count per split category.
- Low-balance alerts exclude debt accounts; dismissed alerts stay dismissed per key.
