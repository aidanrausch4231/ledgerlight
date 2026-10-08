# Python source context

The src-layout contains one `ledgerlight` package. Read
[package context](ledgerlight/context.md) before changing implementation.
Entrypoints: `ledgerlight.cli:main`, `ledgerlight.api:app`. The CLI is the agent
data interface; CLI/API both use shared sync/read/chart functions. Plaid SDK
access is confined to `plaid_client.py`; LLM/remote STT access is confined to
`llm_client.py` (httpx); price APIs (CoinGecko, Yahoo chart) only through
`price_client.py`. `holdings.py` owns manual accounts and holdings. `agent.py` owns the bounded AG-UI loop and
`agent_tools.py` the CLI subprocess capability boundary. `dashboard.py` owns
versioned layouts and durable UI events;
`dashboard_cli.py` / `dashboard_api.py` expose them without duplicating logic.

Dependencies: Python >=3.12, uv, Click, FastAPI, uvicorn, plaid-python,
cryptography, httpx, ag-ui-protocol, FastMCP and stdlib sqlite3; optional voice extra:
faster-whisper small.en/int8/CPU. Root commands: `uv sync --locked`,
`uv run ledgerlight --json version`, `bash scripts/check.sh`. Wheel includes
SKILL.md and the inline MCP Apps chart resource, not the main web UI or deployment files.

Configuration: LEDGERLIGHT_DATA_DIR, LEDGERLIGHT_CONFIG_DIR, PLAID_CLIENT_ID,
PLAID_SECRET, PLAID_ENV, LEDGERLIGHT_FAKE_PLAID. Environment only, no dotenv.
LLM selection: settings llm_provider, overridden by LEDGERLIGHT_LLM_PROVIDER;
OLLAMA_HOST/MODEL, ANTHROPIC_API_KEY, OPENAI_API_KEY and provider model overrides
are environment-only. Fake LLM/STT requires the explicit fake environment value. Tests use temporary storage and fakes,
optional live tests are Sandbox only. Server binds 127.0.0.1 exclusively.

Stage 8: data.accounts_overview shares grouped signed balances, split ratios and
rank/bar/note data across API, CLI, agent READS and read-only MCP. account_names.py
is shared by import and the one-time credit_limit migration. sync_status exposes
honest history_from/history_short date-span evidence. No networth math change.

Stage 7: `history_days` setting/env override requests 365 days by default for
normal Link and Sandbox; validation is shared in money.py. sync.py imports after
exchange, retains per-Item progress and serves status; its server-owned 60-second
worker is bounded to the original 30-minute link window and joined on shutdown.
CLI `sync --wait-history --timeout 600` polls explicitly; `plaid remove` disconnects
for fresh Link without deleting local transactions/annotations. Three additive
Item columns preserve legacy rows with depth 90. Plaid client preserves final-page
update status; fake transitions 30 initial days to requested depth. No new deps.

Stage 6: spending.py adds a split-aware question read and ready chart specs across
CLI/API/MCP; the agent uses it then show_answer. dashboard_default provides one
saved Home layout and undoable reset with CLI/API/MCP mirrors. Casefold is
registered on SQLite connections for Unicode matching in live saved queries.
Chart catalog reads release their cursor before querying on separate connections,
avoiding read/write deadlocks when multiple saved charts mount concurrently.

Built: additive migrations, link/sync, transaction filters, recurring streams,
snapshots/net worth, printable systemd units, budgets, rules, transaction extras,
spending/cash flow, bills, alerts/settings and savings goals. Money operations
are in money.py; money_cli.py and money_api.py contain only interface adapters.
Mutations accept apply=False and return change descriptions. proposals.py stores
--propose commands, then revalidates and applies the same function once in one
transaction only after user confirmation. Cancellation leaves finances untouched.
Stage 3 adds dashboard cards/versions/ui_events, atomic layout changes, undo and
native FastAPI SSE. CLI commands can navigate/filter/highlight all connected tabs.
LEDGERLIGHT_TODAY is an explicit fixed-date test override. Stage 4 adds chart
preview/save/edit/history and HTML CSP documents; voice.py handles bounded
multipart audio with optional CPU or OpenAI transcription. No shell execution,
provider secrets in responses or auto-sent transcripts. Agent calls are limited
to eight tools, 30 seconds/64 KiB per CLI call. Tests mock HTTP/voice and use
synthetic data. Stage 5 `mcp_server.py` exposes explicit stdio tools calling the
same CLI service functions, with proposal-only financial changes and mcp UI
attribution. It never shells out, starts HTTP or applies proposals. Packaged
`resources/chart.html` is a build-time Vega/Lite/Embed bundle with a no-network
Apps bridge and text fallback. The additive source_actor metadata column preserves
legacy actor constraints without rebuilding history. Proposal API adds pending
list; browser supports durable review routes. Not built: spoken replies or LLM
categorization. Never add future-stage stubs.
