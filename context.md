# ledgerlight context

## Purpose and scope
v1 stage 8 local personal finance: Plaid Link/sync, transactions, recurring
streams, daily balance snapshots/net worth, synthetic demos, saved SQL/Vega
charts, budgets, merchant rules, in-app alerts, notes/tags/splits/hide and savings
goals, a Tide Table app shell, versioned card dashboard and live CLI/SSE UI
commands with undo. CLI, FastAPI and React share local SQLite. AG-UI chat,
local/Claude/OpenAI providers, confirmation proposals, chart edit/history,
HTML sandbox and optional push-to-talk are built with offline coverage.
Read `task-briefs/ledgerlight-v1/decisions.md` and `specs/project-brief.md` for
settled scope; `README.md` for operator setup.

Stage 6 adds `spending.py` shared question matching through CLI/API/MCP and the
agent allowlist, answer panels with two saveable chart specs, Enter-to-send,
single-row default Home save/reset with undo, actual actor receipts and user
navigation clearing, reactive Tide Table Vega styling, rolling synthetic demos,
and a proposals SVG icon. No new dependencies. `test_ask_default.py` and
`web/e2e/ask-default.spec.ts` cover synthetic math, scripted two-call answers,
chart pinning, default reset/undo/reload and theme/receipt behavior. Real model
quality is not established by the fake-provider tests.

Stage 7 adds configurable initial history (`history_days`, default 365,
`LEDGERLIGHT_HISTORY_DAYS` override, integer 30–730) to normal/Sandbox Link.
Token creation captures depth once into additive `plaid_link_history` rows keyed
by token hash. Normal exchange carries the original Link token (API/CLI/UI);
Sandbox resolves by public-token hash, including across processes. Settings
changes while Link is open cannot alter recorded depth. Raw tokens are not stored
in this metadata table; metadata has no pruning policy. Live Sandbox subprocesses
require and share Playwright's temporary data/config directories.
Exchange now syncs immediately; additive Item status/depth/oldest-date columns
and live counts power Accounts progress via GET `/api/sync/status` polling.
A lifespan-owned worker retries every 60 seconds within 30 minutes of creation,
resumes only the original window after restart, and stops/joins on shutdown.
`sync --wait-history --timeout 600` supports explicit CLI waiting. Relink removes
remote Item/token but retains local transactions and annotations for matching IDs.
Legacy Items default to 90 days and are offered fresh Link. Fake import progresses
from 30 initial days to a full requested history (365 by default).
Chat successful display-only batches stop without continuation; a 90-second
client timeout aborts and clears Working with a retry hint. Tests:
`tests/test_year_history.py`, SDK/migration extensions in `test_plaid_data.py`,
`web/e2e/year-history.spec.ts`, and coffee no-continuation assertions. Live Sandbox
coverage waits for historical completion and reports oldest dates, but was not run.

Stage 8: Accounts uses the shared `data.accounts_overview()` read across API,
CLI/agent and read-only MCP (now 48 tools total). It groups/ranks signed balances,
shows cash/invested and owed rings, credit limits, empty-account footer and a
responsive Tide Table ledger. Additive credit_limit migration cleans legacy names
once; imports reuse account_names.py. History labels compare actual oldest dates
with requested depth and never claim full history for missing dates. Home uses
Add to Home / Add. Tests: test_accounts_overview.py, MCP/agent read parity and
web/e2e/accounts.spec.ts. No new dependencies, assets or networth math changes.

Manual accounts and holdings: `holdings.py` stores loans, cash, other assets
and crypto/stock holdings as `accounts` rows (`source` manual/holding, item_id
null) plus `manual_details`/`holdings` tables (schema version 2), so overview,
net worth and snapshots share the existing paths. Overview adds Crypto and Other
assets groups. `price_client.py` is the only price network boundary (CoinGecko,
Yahoo chart); tests use `LEDGERLIGHT_FAKE_PRICES=1` or a guarded real client. Writes are
proposable; the server runs a 15-minute price/paydown worker.
Loan payment matching (SCHEMA_VERSION 4): manual loans may carry
`payment_match`/`payment_match_since`; posted, visible outflows from linked
Plaid accounts matching name/merchant are deducted once (`loan_payments`,
floor 0; paid-off loans skipped while another matching loan owes) at the end
of `sync_all` and via `manual apply-payments`; a stored date/amount/name
fingerprint skips the same payment replayed from a different account (relink or
duplicate Item). Plaid `removed` restores the deducted amount inside the Item
transaction. Tests:
tests/test_loan_payments.py, web/e2e/loan-match.spec.ts.

## Components
- [Python source](src/context.md)
- [Python package](src/ledgerlight/context.md)
- [Web](web/context.md)
- [Tests](tests/context.md)
- [Specifications](specs/context.md)
- [CI](.github/context.md) (includes offline Playwright and failure diagnostics)

## Entrypoints and data
`ledgerlight` → `ledgerlight.cli:main`; packaged `src/ledgerlight/SKILL.md` is the
agent contract. Global --json, nonzero JSON errors. API serves built `web/dist`
from source checkouts, binds loopback only. Client module owns all Plaid access;
CLI/API share sync/read functions. SQLite migrations are additive/idempotent;
schema creation, upgrades and version recording share a BEGIN IMMEDIATE write
transaction with a 30-second busy timeout. A thread lock serializes local upgrade
attempts; user_version is rechecked after the database lock and skips current
schemas without stale path caching. tests/test_db_concurrency.py covers thread/
process startup, one-time name cleanup, rollback/retry and warm connections;
Fernet protects access tokens, not the whole DB. No automatic `.env` loading.

## Dependencies and checks
Python >=3.12, uv, Click/FastAPI/uvicorn/plaid-python/cryptography/sqlite3,
httpx, ag-ui-protocol 1.0.0 and FastMCP; optional voice extra uses faster-whisper.
Node >=22.12, pnpm 12.4.2, React/TS/Vite/Vega, react-plaid-link,
react-grid-layout v2, Motion, @ag-ui/client/core 1.0.1 and Playwright chromium.
From root: `bash scripts/check.sh` runs locked installs, Ruff, pytest, build and
offline Playwright. The isolated saved-provider test allows 120s (60s health poll),
gates real status responses without assuming two intercepted reads, and checks
both Settings and the header after release. Playwright retains failure traces;
CI uploads test-results and any playwright-report on failure for seven days.
For isolated HOME settings without a browser cache, the gate uses the runner's
provisioned Chromium cache if present, respecting explicit
PLAYWRIGHT_BROWSERS_PATH overrides. `uv run ledgerlight serve` starts API/UI; `cd web && pnpm dev`
starts the development UI. Optional live Sandbox: see README (not default gate).

## Configuration and constraints
LEDGERLIGHT_DATA_DIR, LEDGERLIGHT_CONFIG_DIR, PLAID_CLIENT_ID, PLAID_SECRET,
PLAID_ENV (sandbox default; production opt-in); LEDGERLIGHT_FAKE_PLAID=1 is the
Plaid fake switch; LEDGERLIGHT_FAKE_PRICES=1 is the price fake; both are visibly
marked in UI. LEDGERLIGHT_E2E_PLAID=sandbox explicitly
selects live Sandbox tests. Never read/commit `.env`, DBs or keys. Unit/browser
storage is temporary; no production calls in testing. README documents environment
setup directly; no example environment file is required.

127.0.0.1 only; SSH tunnel for remote use. Key 0600, config directory 0700;
chart SQL read-only single statement, no query resource budget. Money uses REAL,
net worth subtracts liabilities without FX conversion; snapshots only recorded
dates. Sync isolates item failures and rolls back that item's data/cursor.
Systemd units are printable/installable by the user, never automatically installed.

Stage 2 money operations live in `src/ledgerlight/money.py`, shared by thin
CLI/API adapters. Mutations accept apply=False for stored proposal descriptions. Stage 2 CLI
mutations accept --propose; only user confirmation applies them atomically.
Web pages are split under `web/src/pages/`; API hooks/types under `web/src/lib/`.
Budgets/spending/cash flow exclude pending/hidden and honor signed splits. Rules
preserve raw/fallback categories; sync keeps extras and flags, clears changed
amount splits with a timestamp, and refreshes deduplicated alerts. Savings goals
track linked current balances without moving money. `LEDGERLIGHT_TODAY` explicitly
overrides today's date for deterministic tests; leave unset normally. Threshold
settings are stored locally, not credentials. See SKILL/README for exact semantics.

Stage 3 layout/event logic: `dashboard.py`, with thin `dashboard_cli.py` and
`dashboard_api.py` adapters. Layout/version/event writes are atomic; SSE polls
SQLite, replays after seq/Last-Event-ID and pings every 15 seconds. `uiBus.ts`
owns one stream per tab and exports direct UI actions for later integration.
Tide Table tokens live in `web/src/tokens.css`; fonts are bundled locally with
OFL notices. Drag/resize uses RGL v2 with gap-preserving collision settlement;
Motion only fades inner card content. Mobile stacks without rewriting geometry.
`tests/test_dashboard.py` and `web/e2e/dashboard.spec.ts` cover these paths.
`LEDGERLIGHT_LLM_PROVIDER=fake` selects the deterministic test provider and badge.
Undo is a new version restoring the preceding layout (undoing undo toggles).
Event/version history is retained without pruning. CLI list journals both an
event and layout version; the browser GET snapshot only seeds once. New tabs start at the snapshot cursor, existing tabs replay.

Stage 4: `agent.py` streams native AG-UI, `agent_tools.py` bounds the allowlisted
CLI subprocess, `llm_client.py` owns all LLM/remote transcription HTTP. Browser
`agentTools.ts` executes registered tools through uiBus; HttpAgent returns their
results for mixed/action batches in continuation runs, limited to eight tool
calls per user message. Successful display-only batches terminate locally.
Proposals revalidate and apply once using a shared atomic transaction; cancel
changes no finances. Chart preview/save/edit/history use validated SQL and retain
versions. Legacy chart history is backfilled by schema migration, not history
queries. All allowlisted CLI reads have non-mutation regression coverage;
`dashboard list` is excluded because it journals layout versions/events.
HTML runs in an opaque iframe with CSP first and postMessage rows.
`voice.py` accepts bounded multipart audio; local first-use model download is
explicit, fake STT is offline, transcripts never auto-send. Chat is tab-memory.
Provider selection is saved as llm_provider with an environment override; keys
are environment-only and absent from status/SSE. README documents all variables.
`tests/test_agent.py`, retained `web/e2e/agent-spike.spec.ts` and `agent.spec.ts`
cover these boundaries; real models and real audio quality remain untested.
Stage 5: `mcp_server.py` provides 43 explicit stdio-only FastMCP tools over the
same service functions as CLI. Financial writes only create proposals; MCP has
no apply, arbitrary CLI or provider tools. Secret input is checked before schema
validation; outputs/errors are redacted. `ledgerlight mcp --port` selects web
links, not a listener. `dashboard_list` skips seeding/journaling to remain read-only.
MCP events expose actor mcp. Legacy CHECK-constrained tables gain nullable
`source_actor='mcp'` attribution; existing rows/columns are not rewritten or
removed, and readers expose `COALESCE(source_actor,actor)` as actor.
The packaged UTF-8 `resources/chart.html` bundles Vega/Lite/Embed via
`scripts/build-mcp-chart.mjs` during `pnpm build`. Apps metadata declares no
network domains; sandbox renders whitelisted local specs and receives Apps
JSON-RPC messages, with text spec/rows/dashboard fallback. No MCP HTTP mount.
`#/proposals` and `#/proposals/<id>` provide pending/review pages using stored
redacted summaries, Confirm/Cancel and persistent resolution status.
`tests/test_mcp.py` and `web/e2e/mcp.spec.ts` cover protocol, permissions, reads,
proposal-only writes, live movement and offline Apps rendering. Vendor Apps
clients have not been manually exercised. See README for exact client configs.
Duplicate Plaid links (same institution plus a shared mask/type/subtype account)
are refused with HTTP 409 / CLI JSON; `plaid duplicates` lists existing duplicate
Items and `plaid remove ITEM_ID --delete-local` deletes one with its local data.
Deferred: spoken replies, email/push, Tailscale, SQLCipher and LLM
categorization. Chart SQL outside the agent is still not resource-budgeted;
inside the agent it has the subprocess time/output limits. Histories have no
pruning policy.
