# ledgerlight package context

## Modules and flow
- `cli.py`: global --json, version/demo/chart/serve plus plaid, sync, snapshot,
  accounts, transactions, recurring, networth, systemd print. JSON errors exit 1.
- `api.py`: importable app; health/charts plus matching Plaid/data routes and
  status; JSON error handlers; source-checkout web/dist static mount last.
- `plaid_client.py`: Plaid network boundary, plaid-python request models;
  validates environment/keys, paginates sync, sanitizes errors. Factory uses
  deterministic synthetic FakePlaidClient only for LEDGERLIGHT_FAKE_PLAID=1.
- `sync.py`: exchange/encrypt/store, item metadata, atomic per-item sync
  (accounts, add/modify/remove, recurring replacement, today's snapshots, cursor).
  Failure rolls back all that item's changes, records safe last_error and keeps
  going. Successful retry clears error. Snapshot command uses cached balances.
- `data.py`: parameterized shared queries for account/transaction/recurring/net
  worth reads. Inclusive ISO dates, literal case-insensitive search, bounded
  limits. Credit/loan balances count as liabilities; no FX conversion.
- `db.py`: per-connection foreign keys and 30-second busy timeout. A thread lock
  plus SQLite BEGIN IMMEDIATE serialize initial CREATE IF NOT EXISTS, guarded
  additive ALTERs, data backfills and user_version recording in one transaction
  across threads/processes. Current schemas skip all migration writes via the
  persistent version (no stale path cache); recheck after acquiring each lock.
  Bump SCHEMA_VERSION when SCHEMA, ADDITIONS or backfills change. Failed upgrades
  roll back and can retry; ContextVar/atomic reuse is unchanged.
  recurring_streams and balance_snapshots preserve old/demo rows. Stage 4
  migration backfills legacy charts' current versions idempotently, so chart
  history reads never append rows.
- `crypto.py`: atomic Fernet key creation (0600 file, 0700 directory).
- `config.py`: environment directory overrides, no dotenv.
- `demo.py`: 124 synthetic rolling 120-day transactions, two accounts/streams,
  rolling 90-day synthetic snapshots. Stable transaction IDs reuse all 93 prior-stage
  rows; reseeding updates only demo-owned dates, preserving amounts/categories and
  user extras without daily transaction growth or deletion. Snapshot history is retained.
- `systemd.py`: printable unit strings matching deploy/systemd; no installation.
- `charts.py`: read-only SQL authorization, preview/save/edit/history, HTML CSP
  document helpers. `chart_api.py` mirrors preview/save/edit/history for users.
  Token ciphertext/cursors are not queryable; prior saved-chart current versions
  are preserved when history starts.
- `money.py`: shared rules/preview/apply/undo, transaction extras, monthly budgets,
  split-aware spending/cash flow, bill windows, deduped alerts/settings and goal
  progress. Validated mutations return summaries and accept apply=False. Exact
  Decimal arithmetic over REAL storage; reject non-finite/unrepresentable inputs.
- `money_cli.py` / `money_api.py`: thin Click and typed HTTP adapters registered
  by cli.py/api.py. Routes mounted before static web serving.
- `dashboard.py`: card prop/geometry validation, one-time seed, collision
  displacement, atomic layout snapshots and durable UI events. BEGIN IMMEDIATE
  serializes changes; stale expected_version is rejected. Undo restores the
  preceding snapshot as a new version, so undoing undo toggles back. CLI `list`
  journals a snapshot version and event; browser GET only seeds once. Empty
  layouts stay empty.
- `dashboard_cli.py` / `dashboard_api.py`: dashboard and ui commands/HTTP mirrors;
  whole-layout browser POST; native StreamingResponse SSE, strict after cursor,
  Last-Event-ID resume, 15-second ping and disconnect cleanup. No SSE dependency.
- `SKILL.md`: full packaged CLI command and JSON shape contract.

## Manual accounts and holdings

`holdings.py` owns manual accounts (student/auto/personal loans, cash,
other_asset) and crypto/stock holdings. Rows live in `accounts` with item_id
NULL, `source` manual|holding (additive column, default plaid) and IDs
`manual-<uuid hex>`; details in `manual_details` / `holdings` (ON DELETE
CASCADE; SCHEMA_VERSION 2). Loans store the positive amount owed like Plaid
credit. Mutations accept apply=False; proposals.apply routes holdings.MUTATIONS
to this module. Add/update snapshot today; remove deletes snapshots, alerts and
the account in one transaction. Paydown applies each payment day after
paydown_applied_through up to today (owed × (1+APR/100/12) − payment, cents,
floor 0) in `manual apply-paydown`, `holdings refresh`, `snapshot` and the
server worker; reads never write. Changed balance/payment/day or newly enabled
auto-paydown resets the date to today (no back-charges). sync_all and every
worker tick also snapshot manual/holding accounts (never detached Plaid rows). Remove drops the id from
goals (archiving goals left empty); goals_update filters stale stored ids.
Network never runs inside a write transaction: refresh is load_holdings →
fetch_prices (no DB) → _write_prices; proposals.create pins holdings_add's coin
(resolve_add) and apply prefetches prices before atomic().
`price_client.py` is the only price network boundary: CoinGecko /search and
/simple/price (batched), Yahoo v8 chart (one sequential request per ticker,
User-Agent exactly "Mozilla/5.0" (a full Chrome UA gets 429), per-ticker failures returned as {"error"} so other
tickers update; v7 batch quote returns 401), httpx 10 s timeout, one transport retry,
scrubbed PriceError messages. Only ids/symbols/tickers are sent. FakePriceClient
only for LEDGERLIGHT_FAKE_PRICES=1. Refresh batches per source, sets balance =
quantity × price, snapshots, and keeps the last price with price_error on
failure. `price_worker` runs in the API lifespan beside the history worker and
waits a full 15 minutes before its first tick. `holdings_cli.py` / `holdings_api.py`
are thin adapters; agent READS add manual/holdings list, WRITES the rest (search
is not on the allowlist). Overview adds crypto and other groups plus row
`source` and holding/manual fields (manual kind is `manual_kind`, since `kind`
already exists). Tests: tests/test_holdings.py.

Payment matching (SCHEMA_VERSION 4): manual_details adds `payment_match`
(case-insensitive substring of transaction name or merchant, ≤100 chars) and
`payment_match_since` (ISO date; defaults to today when set or when the text
changes without an explicit date, so nothing earlier is retro-applied; a since
date without a match is refused on add and update). Loans only; refused together
with auto_paydown. `loan_payments(account_id FK CASCADE, transaction_id, amount,
applied_at, source_account_id, txn_date, txn_name, txn_amount)` plus a unique
transaction index record each applied transaction once; `amount` is what was
deducted after the floor at 0; the txn_* fingerprint feeds payments/overview
reads (no join, so orphaned rows keep date and name) and replay detection: a
row with the same date, cents amount and casefolded name as any applied payment
from a different source account is skipped (relink/duplicate Item), while
identical rows in one account all apply.
`manual_apply_payments` (BEGIN IMMEDIATE unless already in a transaction) takes
posted, non-hidden outflows (amount < 0) dated on/after since from linked Plaid
accounts (source plaid, item_id set) not yet in loan_payments. Each goes to one
loan: longest match text, then oldest loan (manual_details rowid), then id,
skipping loans already at 0 while another matching loan owes (all at 0: the
winner records amount 0, still once). Replay checks span all loans, so a
replay cannot move to another loan after the original's loan reached 0.
`sync.sync_all` runs it after auto-paydown and before the unlinked snapshot;
`_sync_item` calls `restore_payments` for removed transactions of that Item
before deleting them (same transaction, so a failed Item rolls it back).
`manual payments ID` / GET manual/ID/payments / MCP manual_payments are reads;
apply-payments is a proposable write (agent WRITES, MCP proposal). Overview
manual rows add payment_match, payment_match_since, payments_applied and
last_payment {date (stored transaction date), amount}.

## Stage 8

`data.accounts_overview()` is the shared signed, grouped/ranked read for CLI
accounts overview, GET accounts/overview, agent READS and MCP accounts_overview.
Legacy accounts/list retains original signs with additive nullable credit_limit.
Groups sort assets by total and Owed last, ranks are continuous, all bars share
one maximum. Empty balances/availability are unranked; institution joins Items.
`account_names.py` cleans replacement/control chars and uppercase alpha runs;
credit_limit's guarded additive migration cleans legacy names exactly once.
Sync stores balances.limit, cleans names with official/subtype/mask fallbacks.
Networth history math is untouched. sync_status adds history_from/history_short;
complete imports later than requested start +14 days (or missing dates) cannot
claim full history. test_accounts_overview.py covers these rules, migrations,
sync and API/CLI parity; existing agent/MCP read non-mutation includes overview.

## Stage 7

`money.history_days()` reads saved `history_days` (default 365) with environment
`LEDGERLIGHT_HISTORY_DAYS` precedence, validating integer 30–730. Settings reads
show saved/default values, not environment overrides. The settings API preserves
JSON integers rather than coercing them to floats; integer strings also work,
while fractional and out-of-range history depths fail without saving.
Depth is user-only (not
proposable). Plaid Link uses LinkTokenTransactions; Sandbox uses request options
transactions days_requested. Choose depth before starting Link; it cannot extend
an existing Item. Each token's effective depth is captured once before the SDK
call, then persisted by SHA-256 token hash in additive `plaid_link_history`.
Normal exchange supplies the original Link token (API `link_token`, CLI
`--link-token`); Sandbox automatically resolves its public-token hash. Unknown
real token history fails before exchange. This survives separate client instances,
processes and settings changes during Link; no raw tokens are stored in metadata.
Metadata is retained without pruning. Fakes use unique issued tokens with stable
synthetic account IDs and test-only support for direct arbitrary public tokens.
Legacy migration adds history_days=90, history_status=NOT_READY,
and nullable oldest_txn_date without rewriting rows.

`sync.link` runs a first sync, retaining safe last_error if it fails. The SDK
paginates to has_more=false and returns the final transactions_update_status;
absent status preserves the stored state. Per-item BEGIN IMMEDIATE transactions
serialize cursor reads/writes across API/CLI/background sync; nested helpers reuse
the ContextVar transaction. Item outputs add status/depth/min-date/count and omit
credentials/cursors. GET sync/status adds effective depth and background_active.
The API lifespan owns a stop Event/thread: retries incomplete Items every 60s
within 1800s of created_at, never extends the window on restart, interrupts waits
and joins in-flight work at shutdown. A ContextVar sync limit checks cancellation
between SDK requests/pages and before commit, rolling back cancelled work without
recording a bank failure. In-flight requests finish before exit (up to 60s);
request timeouts are capped by the remaining CLI/background deadline.

`sync --wait-history --timeout 600` returns per-item progress until complete or
nonzero timeout/error; it polls incomplete Items only. Timeout includes initial
sync and limits SDK request timeouts; zero means one immediate refresh/no retries. `plaid remove` and POST plaid/items/ID/remove
revoke the remote Item, delete local token, detach accounts, and retain local
transactions/extras; fresh Link updates annotations where transaction IDs match.
Different IDs are not deduplicated. Fake tokens carry their chosen depth and
stable account IDs; first sync returns 30 days/INITIAL_UPDATE_COMPLETE, later
sync returns remaining days/HISTORICAL_UPDATE_COMPLETE (365 days by default).
Tests: test_year_history.py plus expanded SDK and migration tests. Live Sandbox
now checks completion and oldest date but is not part of the offline gate.

## Stage 6

`spending.py` is the shared read-only CLI `spending ask` / GET spending/ask / MCP
spending_ask service. It casefolds literal terms (small coffee synonym table),
uses negative split parts, excludes hidden/pending/future rows and returns month,
merchant and latest-10 data plus two build_spec-compatible inline specs with
usermeta title/sql for live save. SQLite connections register deterministic
casefold for identical Unicode matching in saved queries. SQL literals are escaped.
No-match results offer visible category/merchant suggestions. CLI reads remain
non-mutating after additive initialization; the agent uses one read then show_answer.
`dashboard_default` stores one layout/saved_at row; default save/show/reset have
CLI/API mirrors, MCP reset and frontend reset_home. Reset uses normal atomic
version/event writes and undo, with built-in fallback and intentional empty defaults.
Tests: test_ask_default.py, extended allowlist/MCP parity, ask-default Playwright.

## Inputs, outputs and settings
CLI flags, environment, local SQLite and Plaid SDK responses → JSON results,
encrypted access tokens, local balances/transactions and Vega rows. Sign convention
is positive income, negative expense; raw Plaid primary category is preserved.
Item outputs omit tokens/cursor. All SDK error bodies are suppressed to avoid
secret leakage. Snapshot dates use local calendar date; timestamps are UTC.

Settings: LEDGERLIGHT_DATA_DIR, LEDGERLIGHT_CONFIG_DIR, PLAID_CLIENT_ID,
PLAID_SECRET, PLAID_ENV (sandbox default, production allowed for operator use),
LEDGERLIGHT_FAKE_PLAID (exactly 1), LEDGERLIGHT_FAKE_PRICES (exactly 1). Never read `.env` or real storage in tests.
Dependencies: Python >=3.12, Click, FastAPI/uvicorn, plaid-python, cryptography,
sqlite3, httpx, ag-ui-protocol and FastMCP; optional faster-whisper voice extra. From root: `bash scripts/check.sh`, `uv run ledgerlight --json demo seed`,
`uv run ledgerlight serve`. Server is loopback-only.

## Tests, limitations and deferrals
`tests/test_core.py` retains chart/crypto/CLI/loopback coverage;
`tests/test_plaid_data.py` covers migrations, fake/SDK boundary, encryption,
per-item atomicity/cursors/deltas, replacement, snapshots, commands/API/errors.
Default tests never contact Plaid. Browser tests serve the built app with temp
data and config; live Sandbox is explicit and separate.

REAL amounts, no FX conversion or historical account-type tracking. Net worth
only includes recorded dates; failed items do not get a new snapshot. Recurring
product errors currently fail that item's whole sync. Chart SQL materializes
unbounded rows for trusted local use. No authentication/public-host deployment,
no wheel-packaged web build. Not built: spoken replies or LLM categorization.
Chat/providers, HTML sandbox and chart editing/history now have offline coverage.

## Stage 3 tests and limitations
`tests/test_dashboard.py`: idempotent seed, atomic versions/events, undo,
concurrent changes, stale-version protection, all card kinds/props, malformed
requests, every new CLI/API shape, SSE replay/heartbeat/disconnect and resume.
Events and versions are retained without pruning. Built-in card props are empty;
chart requires an existing positive integer chart_id. Deleting the saved chart
later leaves an explanatory card state. Dashboard changes never touch money.
Status exposes test_mode for explicit fake Plaid or LEDGERLIGHT_LLM_PROVIDER=fake;
stage 4 implements that deterministic provider as well as the visible badge.

## Stage 2 semantics and tests
Rules compare casefolded merchant/name; priority then ID decides. Raw Plaid
category and base_category preserve undo even without Plaid categories. Split
categories are explicit and never rewritten by rules. Additive tables: rules,
budgets, tags, splits, alerts, settings and goals; transaction note/hidden/
split_cleared_at/base_category and recurring user_status columns. Sync preserves
user fields, drops splits only on amount changes, and refreshes alerts. Removed
transactions cascade-delete their extras.

Reports exclude pending/hidden; per-part negative amounts count as outflows,
positive as income. Bill window is inclusive, active outflow only; ignored is
excluded, cancel_intent is informational. Low-balance uses available/current,
excludes credit/loan, with global/per-account thresholds. Alert keys persist
across dismissals: bill stream+date, balance account, budget month+category.
Historical alerts remain until dismissed, even if conditions resolve.
Goals sum current linked balances; on_track is null without a date, otherwise
linear from creation to target date; lists include archived goals. No movement.
LEDGERLIGHT_TODAY explicitly overrides calendar dates for deterministic tests;
leave unset normally. `tests/test_money.py` covers math/boundaries, sync
preservation, dry runs, CLI/API shapes and failures; offline browser tests cover
all primary money-management workflows.

## Stage 4 modules and boundaries

- `agent.py`: packaged SKILL + UI guide, native AG-UI SSE, browser registration,
  text/tool/result events, eight-tool cap across continuation runs. Frontend
  results are recorded in HttpAgent messages. The browser now ends successful
  display-only batches locally, continuing only action/mixed/failed batches.
  Client timeout is 90s with stream abort and a fresh conversation for retries.
  No direct financial API/DB
  access by the agent; only the CLI tool. Sanitized stream errors/key redaction,
  including provider tool-call IDs before events, results or continuation messages.
- `agent_tools.py`: real Click parsing plus an explicit command allowlist,
  writes only with --propose, argv subprocess/no shell, 30-second timeout,
  64-KiB combined output cap; children killed/reaped on limits. No linking,
  provider/key changes, direct writes, serve or mcp. Dashboard list is denied
  because it journals versions/events; dashboard state comes from the browser.
- `llm_client.py`: sole httpx LLM/remote transcription client. Ollama's compatible
  streaming chat API, Anthropic Messages, OpenAI chat/transcription and explicit
  fake. Keys remain in request headers only; errors suppress upstream bodies.
  Provider settings/env precedence and status never expose keys. Model/host/key
  environment names/defaults are in README/SKILL; no dotenv loading.
- `proposals.py`: --propose wrappers around every stage 2 CLI mutation, stored
  command/summary/diff, get/apply/cancel HTTP. Apply revalidates and resolves once
  in a ContextVar-shared BEGIN IMMEDIATE transaction (`db.atomic`). No nested
  connection can independently commit partial money changes.
- `voice.py`: 10-MiB multipart bound (stdlib parser), STT status, optional lazy
  small.en CPU/int8 load with loading status, fake fixed transcript. Audio stays
  in memory. First local model use may download weights, never in tests.

`tests/test_agent.py` covers limits, proposals including all mutation families,
concurrent apply/revalidation, provider precedence/mock wire formats and secret
redaction, AG-UI ordering/budget, chart versions/CSP and fake/mock voice. Browser
spike and workflows test HttpAgent, undo, Save/edit/history, confirmations,
recording, HTML fetch denial and real provider setting persistence. No live LLM
or real speech quality claim. SQL outside the CLI tool remains unbudgeted;
chat history is tab-memory; persisted histories/proposals are not pruned.

## Stage 5 MCP

`mcp_server.py` creates a stdio-only FastMCP server with 43 hand-written thin
tools: 15 reads, eight UI/layout writes, chart_save and 19 proposal-only money
actions. `proposals.create` is shared with CLI --propose; no MCP apply tool or
arbitrary CLI execution. SecretGuard rejects configured secrets before tool
schema validation; shared redact handles outputs/errors. Explicit ToolResult
text preserves CLI arrays (including []) and structured data supports Apps.
`ledgerlight [--json] mcp [--port 8000]` emits no startup JSON; the port affects
web links only. Runtime requires Python, not Node or a separate HTTP endpoint.
Dashboard list calls the common snapshot without seed/journal writes. Layout
and UI tools emit actor mcp, with the existing SSE and Undo semantics. SQLite's
legacy CHECK(actor IN user/agent/cli) cannot be widened additively, so migrations
add nullable source_actor constrained to mcp on ui_events/dashboard_versions.
MCP rows retain cli in the compatibility column; readers expose the effective
COALESCE(source_actor,actor). No historical rows, constraints or tables are
rewritten/dropped. This storage choice is covered by migration regression tests.

`resources/chart.html` is tracked UTF-8 and packaged in wheels, generated by
`scripts/build-mcp-chart.mjs` using installed web Vega/Lite/Embed. It contains no
external resource references, declares empty network CSP domains, and handles
the MCP Apps initialize/tool-result/teardown bridge. It permits local Vega
expression compilation, never forwards arbitrary model expressions/URLs and
does not execute HTML charts. Preview/show return spec/rows/dashboard_url for
non-Apps hosts. Chart save reuses validated charts.add directly.
GET /api/proposals lists pending rows; durable web routes load stored/redacted
summary/diff before enabling user Confirm/Cancel. Tests use in-process FastMCP,
raw stdio and a browser host; no vendor client compatibility or live LLM claim.

## Duplicate links

`sync.link(public_token, link_token=None, metadata=None)` refuses a duplicate
Item with `DuplicateLinkError` (a ValueError; API 409, CLI JSON with the same
body): same institution (`plaid_items.institution_id`; name casefold when either
side has none) AND a shared account (mask/type/subtype as text; NULL masks never
match). Link metadata is checked before exchange (no Item created). Without it,
when other Items exist, the exchanged Item's `institution_id` and `item_accounts`
are checked and a duplicate is removed at Plaid before anything is stored. The
first Item skips those calls; `_sync_item` backfills NULL `institution_id` with
one item/get. Same-id relinks still upsert. `PlaidClient` caches item/get per
token so name and id lookups share it. `remove_item(delete_local=True)` deletes
the Item's accounts and their splits, tags, transactions, recurring streams,
snapshots and alerts in the same atomic transaction, after Plaid removal
succeeds. Before that, `_remap_goals` rewrites goals.account_ids (JSON, not an
FK) to the remaining same-institution Item's matching accounts, drops unmatched
ids and archives emptied goals (`deleted.goals_updated`). Placeholder or empty
institution names never match by name. A failed Plaid cleanup in the safety net
still raises the 409 error with `cleanup_failed: true`. `duplicates()` is read-only (agent READ); `--delete-local` is user-only.
Fake Plaid `<identity>@<key>` public tokens give separate Items at institution
`<key>`; plain fake identities are each their own institution. SCHEMA_VERSION 2.
