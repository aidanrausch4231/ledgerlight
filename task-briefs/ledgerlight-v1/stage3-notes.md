# Stage 3 notes (lead, 2026-10-03) — what exists now

Merged as the stage 3 PR. `bash scripts/check.sh`: 154 pytest tests, 4 offline
Playwright tests (plaid, money, dashboard specs).

- Design: Tide Table. Tokens in `web/src/tokens.css`; fonts are local OFL files in
  `web/public/fonts/` (binary; outside worker scope; do not touch). Agent-touched
  UI uses the magenta "notice" token.
- `src/ledgerlight/dashboard.py`: `snapshot(emit_event, actor)`,
  `change(action, actor=..., **args)` for add/move/resize/remove/undo (writes a
  `dashboard_versions` row + `ui_events` row), `ui(action, actor=..., **payload)`
  for navigate/filter/highlight/clear, `events(after)`. Actor values today:
  user, agent, cli (stage 5 adds `mcp`).
- `src/ledgerlight/dashboard_cli.py`, `dashboard_api.py`: `GET /api/dashboard`,
  `POST /api/dashboard/{action}`, `POST /api/ui/{action}`, `GET /api/events`
  (SSE, replay with `after`).
- `web/src/lib/uiBus.ts` exports `navigate`, `filter`, `highlight`, `clear`,
  `add`, `move`, `resize`, `remove`, `undo`, `undoReceipt`, `applyEvent`,
  `useUiBus`, `startUiBus`, `titles`. Stage 4 frontend tools call these with
  actor `agent` so Undo chips appear.
- Pages: `web/src/pages/*.tsx`; cards `web/src/components/DashboardCard.tsx`;
  saved charts `web/src/components/SavedChart.tsx`.
- Workers: never add binary files (snapshots are UTF-8 only).
