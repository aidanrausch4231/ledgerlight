# Tests context

Stage 8: test_accounts_overview.py covers grouping/order/ties/ranks, signed owed,
shared bar scale, cash/credit/loan notes, empty and zero-held/capped ratios,
CLI/API parity, name normalization/fallbacks, one-time stage-7 migration,
nullable limit upsert and 14-day history_short boundaries. Agent READS and MCP
inventory/parity/non-mutation tests include accounts overview. Browser
accounts.spec.ts uses offline fake Plaid and temporary synthetic investments to
check accessible ring, group order/credit sign, rank 1, 390px layout/full-width
Link, live dark tokens, invalidation, honest history/custom depths and Home labels.
It restores synthetic additions after the test; no live account data or calls.

Manual accounts/holdings: test_holdings.py covers every manual kind
(add/list/update/remove, groups/signs, net worth, snapshots), validation, crypto
symbol resolution (ambiguous fake symbol → highest rank), explicit coin id,
stocks, refresh math/snapshots, source errors keeping last price, paydown over
1 and 3 months with floor and idempotence, proposal-only agent writes, API routes,
real-client parsing/scrubbing without network, the worker loop and legacy
upgrade (v1/v2/v3 parametrized; v3 keeps its manual_details row and gains the
match columns, loan_payments and its index; SCHEMA_VERSION 4). conftest clears LEDGERLIGHT_FAKE_PRICES and makes the real
PriceClient._request raise, so any unguarded price call fails. MCP inventory,
parity and proposal tests include the new tools. Browser holdings.spec.ts adds a
crypto holding and student loan through the UI with fake prices, checks groups,
net worth, edit, inline remove and that phone Chat never overlaps balances.

Loan payment matching: test_loan_payments.py uses a scripted FakePlaidClient
subclass (queued added/removed rows, no network) to cover name and merchant
matches (case-insensitive), pending/inflow/hidden/before-since exclusions,
once-only application across repeated syncs, floor at 0 with deducted amounts,
Plaid removal restoring the amount (and rollback with a failed Item), the
specific-then-oldest rule plus skipping paid-off loans (all at 0 → winner, 0),
the unique index, relink (remove_item + link) and duplicate-link replays applied
once (also never moved to another loan), identical same-account payments all
applying, update since-without-match refusal,
auto_paydown/kind/date/length validation, no retro-apply on set/change, today's
snapshot and overview fields, CLI propose/apply, allowlist and API routes.
Agent/MCP read parity and proposal tests include manual payments/apply-payments.
Browser loan-match.spec.ts sets, edits and reloads a match on a loan and checks
the inline auto-paydown conflict error.

Pytest tests isolate LEDGERLIGHT_DATA_DIR and LEDGERLIGHT_CONFIG_DIR in tmp_path;
conftest removes inherited Plaid/LLM credentials, host/model overrides and fake
flags, and selects sandbox.
No real account data, credentials or network calls in unit tests.

`test_db_concurrency.py`: 16 simultaneous threads and two independent spawned
processes initialize fresh and pre-stage-8 schemas in temporary storage. Asserts
all additive columns, schema version, foreign keys, busy timeout and one-time
legacy name cleaning. Warm connections issue no schema/ALTER/write transaction;
failed upgrades roll back schema/data/version and retry. Same-path replacement
and ContextVar atomic connection reuse/rollback also have regression coverage.
Stress with `for i in {1..5}; do uv run pytest tests/test_db_concurrency.py -q || exit; done`.

`test_core.py`: retained crypto permissions, read-only SQL, chart lifecycle and
JSON, synthetic demo idempotency, API and loopback-only CLI serving checks.
`test_plaid_data.py`: old-scaffold additive migration; fake factory and encrypted
access-token storage; SDK pagination and safe errors; add/modify/remove/cursor;
recurring per-item replacement; atomic rollback and failing-item isolation;
snapshot upsert and liability net worth; every new CLI/API route and invalid
inputs; demo snapshots/streams; systemd output matches checked-in units.

`web/e2e/`: Playwright chromium, real built app on a free loopback port with temp
storage. Default fake suite blocks external browser requests and covers linking,
sync, transaction filters/pending, recurring, accounts and home chart at 375px.
Optional LEDGERLIGHT_E2E_PLAID=sandbox enables a separate live spec with Sandbox
keys, client-module token creation, API exchange/sync and eventual data checks.
No production calls, no secret fixtures/logging. Live mode is not default gate.

Dependencies: pytest, httpx/TestClient, Click CliRunner, Playwright chromium.
Root `bash scripts/check.sh` runs locked uv sync, Ruff, pytest, frozen pnpm
install, build and offline e2e; local targeted `uv run pytest -q`.
`cd web && pnpm e2e:install` installs Chromium if missing. Existing dependency
warning about Starlette/httpx is non-failing; no dependency churn to silence it.

`test_money.py`: stage 2 temporary synthetic ledger and explicit fixed date;
rule precedence/apply/undo, exact split rejection, hidden/pending/month-boundary
budget/spending/cashflow math, sync preservation/amount-change clearing, bills,
thresholds/dedupe/dismissals, goals/on-track, non-mutating dry runs and every
CLI/API command/route plus JSON validation errors. `conftest` clears inherited
LEDGERLIGHT_TODAY; each deterministic fixture opts in explicitly.
`web/e2e/money.spec.ts`: budget progress, rule match preview and category change,
transaction notes/tags/hide/splits, bills, threshold/alert dismissal and goals.
Offline server sets a fixed date; live mode removes it.

`test_dashboard.py`: atomic layout/version/event writes, one-time seeding and
intentional empty layouts, deterministic collisions, all card kinds/props,
undo-as-version, concurrency and stale edits, invalid requests, every dashboard/ui
CLI and API shape, SSE replay/heartbeat/disconnect and Last-Event-ID behavior.
`web/e2e/dashboard.spec.ts`: invokes the actual CLI against the browser server's
temporary storage while the page is open; live move/add/resize/remove, receipt
Undo, navigation/filter/clear/highlight without reload, one stream per tab,
real RGL drag and reload, keyboard movement, dark/system theme and every page at
375px. Drag setup deliberately moves between different rows at the same column,
waits for both SSE coordinates, then uses handle actionability rather than a fixed
sleep before pointer input; persistence and reload assertions remain required. Explicit fake LLM env now selects the deterministic stage 4 provider and badge.
Playwright config shares a temporary root through LEDGERLIGHT_E2E_STORAGE;
serve.py removes it on shutdown. Tests never use user-default storage.

`test_agent.py`: Click-parsed allowlist including disguised --propose values,
dashboard-list denial, full database comparisons for every allowlisted read
(repeated, with and without demo/dashboard seeding), legacy-chart migration
backfill/idempotence/history preservation, no-shell literal metacharacters,
real subprocess timeout/output cap and cleanup,
all stage 2 proposal dry runs/apply, concurrent apply-once, cancel, stale split
revalidation/rollback, provider precedence and fake restrictions, mocked httpx
stream adapters for all three providers, key redaction across split SSE tokens
and provider tool-call IDs (backend results and browser continuations, including
embedded secrets), sanitized failures, eight-tool bound, AG-UI order/backend results, chart
preview/save/edit/history, CSP injection and token-column denial, STT status,
mocked optional engine and bounded multipart fake transcription. No live LLM/STT
calls or model downloads.

`e2e/agent-spike.spec.ts`: retained step-0 proof, real Vite/React 19 HttpAgent
registration/navigation/returned result. `e2e/agent.spec.ts`: live agent layout
move/Undo, chart Save/reload/edit/history, budget Confirm/Cancel, MediaRecorder
with Chromium fake audio + fake STT (no auto-send), HTML iframe fetch denial and
opaque origin, mobile width, provider switch/reload on an extra loopback server
without env override. Delayed real provider-status responses also verify that
an unsaved selection survives background refreshes and saves correctly.
Every server uses synthetic temporary directories. Fake
voice flags only affect test Chromium. Live Plaid remains explicitly separate.

`test_mcp.py`: exact documented 43-tool inventory/annotations, Apps resource
metadata and offline bundle, seeded/unseeded repeated read parity with CLI and
full ledger non-mutation checks, all UI events/version attribution and chart
save, all 19 proposal-only actions, web apply-once/cancel/pending list, configured
secret rejection/redaction, forbidden tools/arguments/provider/SQL writes,
legacy actor attribution migration, and raw stdio stdout (with/without --json).
`web/e2e/mcp_client.py` drives FastMCP in-process over shared temporary test
storage while the browser is open. `mcp.spec.ts` proves live move/no reload,
pending and deep-link confirmations/resolution persistence, and the packaged
Apps resource rendering through its JSON-RPC host bridge with network/parent
access denied. Bundle is rebuilt by pnpm build and packaged for Python-only
installation. Vendor clients and remote SSH deployment are not exercised.

Stage 6: test_ask_default.py covers casefold/synonyms across fields, split/sign and
hidden/pending/date boundaries, aggregates, empty suggestions, CLI/API errors,
saveable query parity, rolling demos with stable IDs across consecutive dates and
month/year boundaries, full stage-5 demo upgrade without duplicates, preservation
of transaction fields/tags/splits and unrelated data, single-row defaults, seed fallback,
empty defaults, save/reset/undo, a concurrent chart-catalog/layout-write deadlock regression,
and exactly spending ask then show_answer through
the real fake-provider AG-UI loop. Agent read non-mutation and MCP inventory/parity
include spending_ask; MCP attribution includes dashboard_reset_default.
web/e2e/ask-default.spec.ts covers Enter/Shift+Enter, two answer charts, pinning,
replacement/dismiss/reload, live theme tokens, default save/reset/undo/reload and
receipt clearing. Existing CLI/MCP browser expectations assert actual actors.

Stage 7: `test_year_history.py` covers validated saved/env history depth, settings
API integer/string bounds and persistence, rejection of fractional/out-of-range
values without changing the saved setting, fixed
Item depth, immutable per-token depth across setting/env changes during and after
SDK token creation (normal/Sandbox), separate client instances, CLI/API exchange,
unknown-history rejection before network, hash-only metadata, independent fake
tokens, initial 30-day/import-complete progression and oldest dates, status API,
remove/fresh-Link note/tag/split retention, completion/stalled-window/background
shutdown behavior, and CLI --wait-history success/polling/timeout/errors.
`test_plaid_data.py` now asserts SDK Link/Sandbox days_requested=365 and 540,
final-page status, additive legacy depth=90/status/date migration without changing
old ciphertext, and 365-day synthetic import counts. conftest clears inherited
LEDGERLIGHT_HISTORY_DAYS. `web/e2e/year-history.spec.ts` verifies Accounts live
progress through the real 60-second server worker, full-year dates in Transactions,
relink annotations and 90-second chat timeout/retry using the browser clock.
Coffee coverage asserts Working is gone within 5s and only one AG-UI request for
backend read plus display. The opt-in live Sandbox spec waits up to 600s for
historical completion and reports oldest dates; not run during this stage.
Its token subprocess requires LEDGERLIGHT_E2E_STORAGE and explicitly shares the
server's temporary data/config paths, never user-default storage.

Duplicate links: `test_duplicate_links.py` uses a spy FakePlaidClient to prove
metadata refusal before exchange, the post-exchange safety net (remote removal,
nothing stored), API 409 and CLI JSON bodies, allowed disjoint accounts, NULL
masks, different institutions with equal masks, legacy NULL institution_id name
fallback plus sync backfill, same-Item relink, `--delete-local` scope (only that
Item's rows; overview/net worth halve), Plaid failure leaving rows intact,
default remove unchanged, and `duplicates()` grouping/keep rules. Goal tests
cover remap (progress kept, goals_update still valid), dropped unmatched ids,
archived empty goals and plain remove leaving goals alone; also safety-net
cleanup failure (`cleanup_failed`) and placeholder institution names.
`web/e2e/duplicate-link.spec.ts` rewrites the fake Link exchange to a second
synthetic Item of the same bank and checks the server's 409 message is shown.

Not covered: real provider/model availability, real speech accuracy or production
accounting. Never persist synthetic test DBs in user defaults or add real tokens
to fixtures/reports.
