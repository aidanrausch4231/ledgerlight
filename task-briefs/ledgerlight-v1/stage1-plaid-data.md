# Stage 1 — Plaid link, sync, transactions, recurring, snapshots, net worth

GOAL: link Plaid accounts, sync them into SQLite, and show transactions,
recurring items and net worth in the CLI, API and web app, with a full local
test gate including Playwright.

REPO: personal/ledgerlight (branch `v1-stage1-plaid-data`, base `main` d2108c0)

Read first: `task-briefs/ledgerlight-v1/decisions.md` (binding), then
`specs/project-brief.md`, `context.md`, `src/ledgerlight/context.md`,
`web/context.md`, `tests/context.md`, `src/ledgerlight/SKILL.md`.

## Current code (scaffold facts)

- `src/ledgerlight/db.py:8-37` one `SCHEMA` string run by `executescript` on
  connect: tables `accounts(id, name, balance)`, `transactions(id, account_id,
  date, name, merchant, amount, category)`, `charts`, `plaid_items(id,
  institution, access_token_enc)`. No migrations.
- `src/ledgerlight/cli.py` (121 lines): `JsonGroup` (cli.py:18-38) turns
  ClickException/ValueError/sqlite3.Error/OSError into `{"error": ...}` exit 1;
  `emit()` cli.py:15. Commands: version, demo seed, chart add/list/show/remove,
  serve --port.
- `src/ledgerlight/api.py` (30 lines): module-level `FastAPI` app; GET
  `/api/health`, GET `/api/charts`; mounts `web/dist` at `/` when present.
- `src/ledgerlight/crypto.py`: `encrypt(str)->str`, `decrypt(str)->str`.
- `src/ledgerlight/config.py`: `data_dir()`, `config_dir()`, `db_path()`.
- `src/ledgerlight/demo.py`: synthetic 90-day seed (2 accounts, 93 txns).
- `web/src/App.tsx` (66 lines): one page, fetches `/api/charts`, renders with
  vega-embed. No router. `web/src/index.css` plain CSS.
- `tests/conftest.py` autouse `isolated_storage`; `tests/test_core.py` 15 tests.

## Build

1. Schema (additive, idempotent): extend `accounts` with `item_id`, `type`,
   `subtype`, `mask`, `available` (nullable), `currency`; extend `plaid_items`
   with `cursor`, `created_at`, `last_synced_at`, `last_error`; extend
   `transactions` with `pending`, `plaid_category` (raw Plaid
   personal_finance_category primary), `removed` handling = delete row. New
   tables: `recurring_streams(id, account_id, direction in|out, description,
   merchant, frequency, average_amount, last_amount, last_date,
   predicted_next_date, is_active, status, category)`, `balance_snapshots(date,
   account_id, current, available, PRIMARY KEY(date, account_id))`.
   Keep the demo seed working (demo rows may leave new columns null) and add
   synthetic recurring rows and 90 days of snapshots to the demo seed.
2. `src/ledgerlight/plaid_client.py`: thin wrapper with methods
   `create_link_token()`, `exchange_public_token(public_token)` ->
   (item_id, access_token), `institution_name(item_id/access_token)`,
   `accounts(access_token)`, `transactions_sync(access_token, cursor)` (loop
   until `has_more` false), `recurring(access_token)`,
   `sandbox_public_token()` (sandbox env only). Factory `get_client()` returns
   the real client, or `FakePlaidClient` with deterministic synthetic data when
   `LEDGERLIGHT_FAKE_PLAID=1`. Clear error JSON when keys are missing.
3. `src/ledgerlight/sync.py`: `link(public_token)` stores the encrypted token
   and institution; `sync_all()` for each item: accounts upsert, transactions
   sync with cursor (added/modified upsert, removed delete), recurring
   streams replace-per-item, then today's snapshot upsert. Records
   `last_synced_at`/`last_error` per item; one failing item does not stop others.
4. CLI (all `--json`): `plaid link-token`, `plaid exchange <public_token>`,
   `plaid items`, `plaid sandbox-link` (sandbox only: create + exchange),
   `sync`, `snapshot` (today only), `accounts list`, `transactions list
   [--account --since --until --category --search --limit (default 100)]`,
   `recurring list [--direction]`, `networth [--days 90]` (date, total rows
   from snapshots), `systemd print` (prints a user `.service` and `.timer`
   pair: timer `OnCalendar=*-*-* 00/6:00:00`, `Persistent=true`, service runs
   `ledgerlight sync`; sync already takes the daily snapshot). Do not install
   anything into systemd. Also add the same two unit files under `deploy/systemd/`.
5. API: refactor `api.py` to keep `app` importable but add the new routes:
   POST `/api/plaid/link-token`, POST `/api/plaid/exchange` `{public_token}`,
   GET `/api/plaid/items`, POST `/api/sync`, GET `/api/accounts`, GET
   `/api/transactions` (same filters as CLI), GET `/api/recurring`, GET
   `/api/networth?days=`, GET `/api/status` (`{fake_plaid: bool, plaid_env}`).
   Errors return JSON `{"error": ...}` with 4xx/5xx. CLI and API call the same
   Python functions; no logic duplicated.
6. Web: add `react-router-dom` (or a tiny hash router; choose the smallest) with
   pages Home (existing saved charts + a net worth line chart from
   `/api/networth`), Transactions (filter bar + table, pending marked),
   Recurring (in/out lists, next date, amount), Accounts (list, balances,
   "Link account" button using `react-plaid-link`, "Sync now" button, per-item
   last sync / error). Show a "test mode" badge when `/api/status` reports a
   fake. Plain CSS, readable, keyboard accessible, works at 375px width.
7. Tests: pytest for schema migration on an old scaffold DB, plaid fake,
   sync add/modify/remove/cursor, recurring replace, snapshots upsert, every
   new CLI command JSON shape and error exit, every new API route, token
   stored encrypted (raw token never in DB), systemd print content.
8. Playwright: `web/playwright.config.ts`, `web/e2e/`. A `webServer` that runs
   `uv run ledgerlight serve --port <free>` from repo root with temp data and
   config dirs and `LEDGERLIGHT_FAKE_PLAID=1` (built `web/dist` served by the
   API). Specs: link via API (`plaid sandbox-link` equivalent through the
   fake), sync, transactions page filters, recurring page, accounts page shows
   balance, home shows net worth chart. Plaid live spec per decisions.md
   (`LEDGERLIGHT_E2E_PLAID=sandbox`), skipped otherwise. Add web scripts
   `e2e` and `e2e:install`.
9. `scripts/check.sh` (executable) per decisions.md: the full gate, ending with
   `cd web && pnpm build && pnpm e2e`. CI: do not edit `.github/` (lead does).
10. Docs: SKILL.md (every new command + JSON shapes), README (Plaid Trial keys,
    linking, sync, systemd install steps for the user to run themselves),
    context.md files, AGENTS.md scope line per decisions.md.

## OUT OF SCOPE

Budgets, merchant rules, alerts (stage 2). Chat, LLM providers, chart editing,
HTML sandbox (stage 3). `.github/`. Any production Plaid call.

## DONE WHEN

`bash scripts/check.sh` exits 0 from the repo root (ruff, pytest, frozen
installs, build, Playwright offline suite all pass), and
`uv run ledgerlight --json systemd print` returns JSON with `service` and
`timer` strings.
