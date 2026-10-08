# Stage 3 — chosen visual design, app shell, live card dashboard, UI command bus

GOAL: rebuild the web app in the owner's chosen design with a card dashboard that the
user can drag and that CLI commands can change live over SSE, with undo.

REPO: personal/ledgerlight (branch `v1-stage3-ui`, from main after stage 2 merged)

Read first: `task-briefs/ledgerlight-v1/decisions.md` (binding),
`task-briefs/ledgerlight-v1/stage2-notes.md` (what exists), the chosen design
`design/mockups/CHOSEN.md` (names the direction file and token file — build to
them exactly), then root/component `context.md` files and `src/ledgerlight/SKILL.md`.

## Approved dependencies

`react-grid-layout` v2 (22k stars), `motion` (33k stars). No other UI framework.
If react-grid-layout fails with React 19, stop and report (do not swap libraries).

## Build

1. App shell per the chosen design: nav, header with alert bell, light/dark
   (system default + toggle), 375px support, keyboard accessible, visible focus.
   Restyle every existing page (Transactions, Recurring/Bills, Accounts,
   Budgets, Rules, Goals, Settings) to the design tokens. Tokens live in one
   CSS file as custom properties.
2. Dashboard storage: `dashboard_cards(id TEXT PRIMARY KEY, kind, props JSON,
   x, y, w, h, created_at, updated_at)` plus `dashboard_versions(version
   INTEGER PRIMARY KEY, layout JSON, actor user|agent|cli, action, created_at)`.
   Every layout change writes a new version. `undo` restores the previous
   version (and is itself a version). Seed a default layout on first run.
3. Card kinds (built in, props validated): `spending_vs_last_month`,
   `cashflow`, `upcoming_bills`, `net_worth`, `budgets`, `goals`, `alerts`,
   `recent_transactions`, `top_merchants`, `chart` (props: chart_id, a saved
   Vega-Lite chart). Each card reads the stage 2 shared queries via API.
4. UI command bus: CLI (`--json`) `dashboard list|add|move|resize|remove|undo`
   and `ui navigate <page>|filter <page> key=value...|highlight <target>|clear`.
   Each command writes a `ui_events(seq INTEGER PRIMARY KEY, type, payload
   JSON, actor, created_at)` row; dashboard commands also write a version.
   API mirrors: `GET /api/dashboard`, `POST /api/dashboard/...`, `POST
   /api/ui/...`, and `GET /api/events?after=<seq>` — native FastAPI
   `StreamingResponse` SSE (no sse-starlette), `: ping` every 15 s, replay from
   `after` on reconnect, one stream per tab.
5. Browser: one `uiBus` module that applies events: navigate (hash router),
   filter (page filter state), highlight (pulse outline 2 s on the target,
   targets addressed by stable `data-ui-id`), dashboard add/move/resize/remove
   (react-grid-layout controlled layout; move/resize animate with its CSS
   transitions; add/remove animate with Motion `AnimatePresence` inside the
   card, never `layout` on grid items). After any non-user change show an Undo
   chip ("Agent moved Dining vs last month · Undo"). User drags/resizes POST
   the new layout (actor user). Stage 4's agent will call the same `uiBus`
   functions directly, so export them.
6. Tests: pytest for versions/undo, event rows, SSE replay after `after`,
   props validation, every new CLI/API shape. Playwright: run
   `uv run ledgerlight --json dashboard move <card> --x 0 --y 0` (and add,
   remove, `ui navigate transactions`, `ui highlight`) from the test while the
   page is open, assert the DOM updates without reload, click Undo and assert
   the previous layout; drag a card and reload to see it persisted; dark mode
   toggle; 375px layout has no horizontal scroll.
7. Docs: SKILL.md (new commands, card kinds, event types), README, context.md.

## OUT OF SCOPE

Chat agent, LLM, voice (stage 4), MCP (stage 5), `.github/`, `.env*`.

## DONE WHEN

`bash scripts/check.sh` exits 0 from the repo root.
