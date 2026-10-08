# Stage 2 — budgets, merchant rules, alerts, notes/tags/splits, savings goals

GOAL: add the money-management data features (budgets, rules, alerts,
transaction notes/tags/splits/hide, savings goals) to the CLI, API and basic web
pages.

REPO: personal/ledgerlight (branch `v1-stage2-data`, from main after stage 1 merged)

Read first: `task-briefs/ledgerlight-v1/decisions.md` (binding),
`task-briefs/ledgerlight-v1/stage1-notes.md` (what exists), then root and
component `context.md` files and `src/ledgerlight/SKILL.md`.

## Build

1. Effective category = user rule result, else Plaid primary category, else the
   existing `category`. Store the effective value in `transactions.category`
   and keep `plaid_category` raw so rules can be undone. Hook rules at
   `sync._category` (sync.py:68) and in a re-apply function.
2. `merchant_rules(id, match_field merchant|name, match_type exact|contains,
   pattern, category, priority, created_at)`. Case-insensitive. Lowest priority
   number wins, then lowest id. Rules apply during sync; `rules apply`
   re-applies to all rows; removing a rule re-applies so rows fall back.
3. Transaction extras: `transactions.note TEXT`, `transactions.hidden INTEGER
   DEFAULT 0` (hidden = excluded from budgets, spending and cash flow, still
   listed with a marker); `transaction_tags(transaction_id, tag, PRIMARY KEY
   both)`; `transaction_splits(id, transaction_id, category, amount)` — split
   amounts must sum exactly to the transaction amount (reject otherwise);
   a split transaction counts per split category in budgets and spending.
   Sync must never overwrite note/hidden/tags/splits; if Plaid changes the
   amount of a split transaction, drop its splits and record that in
   `last_error`-style notes on the transaction (`split_cleared_at`).
4. `budgets(category PRIMARY KEY, monthly_limit, created_at, updated_at)`.
   `budgets report [--month YYYY-MM]`: category, limit, spent (outflows only,
   pending and hidden excluded, splits honored), remaining, percent.
5. Spending/cash flow queries (shared module): `spending summary --month`
   (total out, by category, top merchants, same day-of-month cumulative line
   for this month and last month), `cashflow --months 6` (income vs spending
   per month). These power stage 3 dashboard cards; build query + CLI + API
   now.
6. Upcoming bills: `bills upcoming --days 30` from active outflow recurring
   streams (predicted date, amount, merchant, account) plus a user flag
   `recurring_streams.user_status` in {null, 'cancel_intent', 'ignored'} set by
   `recurring mark <id> --status`. Sync must keep `user_status`.
7. Alerts (in-app only): `alerts(id, kind bill|low_balance|budget_over, key
   UNIQUE, account_id, title, detail, due_date, created_at, dismissed_at)`.
   `alerts refresh` creates bill alerts for upcoming bills within `bill_days`
   (default 3), low-balance alerts below `low_balance_threshold` (default 100,
   per-account override `low_balance_threshold:<account_id>`), budget-over
   alerts when a category passes 100%. Dedupe by key. Sync runs refresh.
   `settings(key PRIMARY KEY, value)` holds thresholds.
8. Savings goals (tracking only, no money movement): `goals(id, name,
   target_amount, target_date NULL, account_ids JSON, created_at, archived_at)`.
   Progress = sum of current balances of linked accounts; report percent,
   remaining, and on-track (linear from created_at to target_date) when a date
   exists.
9. CLI (`--json` everywhere): `rules add|list|remove|apply`,
   `budgets set|list|remove|report`, `txn note <id> <text>`, `txn hide|unhide
   <id>`, `txn tag <id> <tag>...`, `txn untag <id> <tag>`, `txn split <id>
   --part CATEGORY=AMOUNT ...`, `txn unsplit <id>`, `transactions list --tag`,
   `spending summary`, `cashflow`, `bills upcoming`, `recurring mark`,
   `alerts list [--all]|dismiss|refresh`, `settings get|set`,
   `goals add|list|update|archive`. Every data-changing command must be a thin
   call into one Python function (stage 4 will add a `--propose` mode that
   returns the change without applying it — design functions so a dry-run
   description is easy: `fn(..., apply=True)` returning a change summary).
10. API: matching routes under `/api/...`, same functions.
11. Web (basic, functional; stage 3 restyles): split pages into
    `web/src/pages/`. Budgets page, Rules page (with match-count preview),
    Goals page, Bills list, alert banner with dismiss on every page, settings
    form for thresholds, and on Transactions: note, tags, hide, split editor,
    "create rule from this".
12. Tests: pytest for rule precedence/apply/undo; split validation and budget
    math with splits/hidden/pending across a month boundary; sync preserving
    user fields; spending/cashflow math; bills window; alert create/dedupe/
    dismiss/thresholds; goal progress and on-track; every CLI/API shape and
    error exit. Use a test-only fixed date `LEDGERLIGHT_TODAY=YYYY-MM-DD`
    (ignored unless set). Playwright (new spec files, fake Plaid): set a budget
    and see progress, add a rule and see a transaction recategorized, split a
    transaction, see and dismiss a low-balance alert, create a goal and see
    progress.
13. Docs: SKILL.md (every new command + JSON shape), README, context.md files.

## OUT OF SCOPE

Visual redesign and dashboard cards (stage 3), chat/LLM (stage 4), MCP
(stage 5), email/push, LLM categorization, `.github/`, `.env*` files.

## DONE WHEN

`bash scripts/check.sh` exits 0 from the repo root.
