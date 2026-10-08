# Stage 5 — MCP server (FastMCP, stdio) with MCP Apps chart viewer

GOAL: external agents (Claude Code, Claude Desktop, Cursor, Codex) use
ledgerlight through `ledgerlight mcp` over stdio: read data, make charts, drive
the live dashboard, and propose changes the user confirms in the web app.

REPO: personal/ledgerlight (branch `v1-stage5-mcp`, from main after stage 4 merged)

Read first: `task-briefs/ledgerlight-v1/decisions.md` (binding),
`task-briefs/ledgerlight-v1/stage4-notes.md`, root/component `context.md`,
`src/ledgerlight/SKILL.md`, and research
`task-briefs/ledgerlight-v1/research/web-mcp-server.md`.

## Approved dependency

`fastmcp` (PrefectHQ/fastmcp). stdio transport only; no HTTP mount.

## Build

1. `src/ledgerlight/mcp_server.py` + CLI `ledgerlight mcp` (stdio; it must not
   print anything else to stdout). Hand-written thin tools calling the SAME
   Python functions the CLI uses (no subprocess, no logic duplication):
   - Read (annotate `readOnlyHint: true`): accounts, transactions (filters),
     recurring, bills_upcoming, budgets_report, spending_summary, cashflow,
     networth, goals, alerts, rules, chart_list, chart_show, chart_preview,
     dashboard_list.
   - Live UI (writes UI state only; `destructiveHint: false`): ui_navigate,
     ui_filter, ui_highlight, dashboard_add/move/resize/remove/undo — they write
     the same `ui_events`/versions as the CLI (actor `mcp`), so an open browser
     updates live over SSE.
   - Data changes: `propose_<action>` tools only, mapping to stage 4
     `--propose`; result tells the user to Confirm in the web app at
     `http://127.0.0.1:<port>/#/proposals/<id>` and returns the summary. No MCP
     tool applies a proposal. Add a web route `#/proposals/<id>` (and a list of
     pending proposals) if stage 4 did not.
   - `chart_save` (saving a previewed chart is allowed directly).
2. MCP Apps chart viewer: a `ui://ledgerlight/chart` HTML resource (MCP Apps
   extension) that renders a Vega-Lite spec + rows; bundle vega/vega-lite/
   vega-embed inline into the resource at build time (no CDN) and declare an
   empty network CSP. `chart_preview`/`chart_show` link to it via the tool's UI
   metadata; their text result also includes the spec and the dashboard link
   as fallback for hosts without MCP Apps (Claude Code, Codex).
3. Docs: README section with exact client configs: Claude Code
   (`claude mcp add ledgerlight -- ledgerlight mcp`), Claude Desktop JSON,
   Cursor, Codex, and remote via `ssh host ledgerlight mcp`. SKILL.md and
   context.md updates.
4. Tests: in-process FastMCP client: tool list matches the documented set,
   annotations present, read tools return the same JSON as the CLI, UI tools
   create `ui_events` rows, propose tools create proposals and change no data,
   no tool can apply a proposal or run arbitrary CLI args, stdio server prints
   nothing but protocol to stdout, the `ui://` resource contains no external
   URLs. Playwright: with the page open, call the MCP `dashboard_move` tool
   from the test (in-process client via a small Python helper) and assert the
   card moves live.

## OUT OF SCOPE

HTTP/Streamable transport, MCP auth, elicitation-based writes, `.github/`,
`.env*`.

## DONE WHEN

`bash scripts/check.sh` exits 0 from the repo root.
