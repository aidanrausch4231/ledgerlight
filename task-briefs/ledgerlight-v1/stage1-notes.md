# Stage 1 notes (lead, 2026-10-03) — what exists now

Merged as the stage 1 PR. 43 pytest tests + offline Playwright pass via
`bash scripts/check.sh`.

- `src/ledgerlight/db.py` — SCHEMA + additive migrations (db.py:83). Add new
  tables/columns the same way.
- `src/ledgerlight/plaid_client.py` — real client + `FakePlaidClient`
  (`LEDGERLIGHT_FAKE_PLAID=1`). Extend the fake's synthetic data when a stage
  needs new fixtures (e.g. a low-balance account, a bill due soon).
- `src/ledgerlight/sync.py` — `link`, `sandbox_link`, `items`, `snapshot`,
  `_category(row)` (sync.py:68, the place to hook merchant rules), `_sync_item`,
  `sync_all`.
- `src/ledgerlight/data.py` — shared read queries used by CLI and API:
  `accounts`, `transactions(...)`, `recurring`, `networth`. Put new shared logic
  in modules like this, never inside CLI or API handlers.
- `src/ledgerlight/cli.py` (215 lines), `src/ledgerlight/api.py` (117 lines).
- Sign convention: negative = expense/outflow, positive = income (Plaid's sign is
  inverted on import). Raw Plaid primary category is kept in `plaid_category`.
- `web/src/App.tsx` (198 lines) holds every page with a hash router
  (`#/`, `#/transactions`, `#/recurring`, `#/accounts`). When you add pages,
  split pages into `web/src/pages/*.tsx` and shared bits into
  `web/src/lib/*.ts`; keep the hash router.
- Playwright: `web/playwright.config.ts`, `web/e2e/serve.py` (starts the server
  with temp dirs + fakes), `web/e2e/plaid.spec.ts`. Add new spec files; keep the
  live Sandbox spec skipped unless `LEDGERLIGHT_E2E_PLAID=sandbox`.
- `scripts/check.sh` is the gate; it unsets live Plaid vars. Do not weaken it.
- Known gap: README no longer mentions `.env.example` (workers cannot see
  `.env*` files). The file exists in the repo with safe placeholders; README may
  reference it by name. Never try to create or edit it.
