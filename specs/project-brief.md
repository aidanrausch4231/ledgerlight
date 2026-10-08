# ledgerlight — settled project brief

Decisions confirmed by the owner, 2026-09-24. Product: a free, self-hosted personal
finance alternative, open source under the MIT License. Branding is ledgerlight. The GitHub
repository `<owner>/ledgerlight` is public; only the lead creates it and pushes.

## Architecture and interfaces

- One Python package, Python >=3.12, uv, Click CLI, FastAPI, plaid-python,
  stdlib sqlite3, cryptography Fernet. React + TypeScript + Vite under `web/`, pnpm.
- CLI-Anything method: the application's own agent-native CLI is the single
  interface the agent uses to data. Global `--json` machine output on every
  command; bundled `SKILL.md` documents commands and output shapes. The future
  chat agent's tools are CLI commands, not a separate data API.
- FastAPI serves the built `web/dist` when present. The scaffold offers
  `/api/health` and `/api/charts`; the latter powers the web shell.
- SQLite charts contain a read-only SQL query plus a validated Vega-Lite JSON
  spec, with versions. Edits increment the version. Chart format is Vega-Lite
  (lead decision). Save pins a chart to the home page of saved charts.
- Future escape hatch: custom HTML in a sandboxed iframe with no network. It is
  not part of this scaffold.

## Security and local deployment

- Fernet encrypts Plaid access tokens. Key auto-generated on first use at
  `~/.config/ledgerlight/key`, file mode 0600 and key directory 0700. Override the
  directory with `LEDGERLIGHT_CONFIG_DIR`.
- DB: `~/.local/share/ledgerlight/ledgerlight.db`, override directory with
  `LEDGERLIGHT_DATA_DIR`. DB, `.env`, keys never committed. No SQLCipher yet.
- Server binds 127.0.0.1 only, not configurable. Remote use is an SSH tunnel:
  `ssh -L 8000:127.0.0.1:8000 user@host`. No public deployment or authentication.
- Every user supplies their own Plaid and LLM keys. Get free Plaid Trial keys
  (10 Items); use only synthetic or Plaid Sandbox data in tests.
- CI runs gitleaks with full-history checkout. Never put personal account data
  in fixtures, prompts, screenshots, commits or reports.
- Environment names: PLAID_CLIENT_ID, PLAID_SECRET, PLAID_ENV (sandbox default),
  LEDGERLIGHT_LLM_PROVIDER, OLLAMA_MODEL, ANTHROPIC_API_KEY, OPENAI_API_KEY,
  LEDGERLIGHT_DATA_DIR, LEDGERLIGHT_CONFIG_DIR. No automatic `.env` loading.

## Stage 1: scaffold built now

- Root contract, context files per component, setup documentation, safe example
  environment, ignored local data, reproducible uv/pnpm lockfiles.
- Idempotent SQLite schema: accounts; transactions with id, account_id, date,
  name, merchant, amount, category; charts with id, title, sql, spec_json,
  version, created_at, updated_at; plaid_items with id, institution,
  access_token_enc. Accounts have id, name and illustrative balance.
- Working config, SQLite and encryption helpers; synthetic 90-day demo seed.
- Chart SQL validation: exactly one statement on a read-only connection; reject
  invalid SQL and writes. Generated bar/line/area/arc specs use first column for
  category (x, or color for arc) and second column for value (y or theta).
- Chart add/list/show/remove, and internal save-by-ID that bumps version. No
  editing CLI or UI in this stage. Results contain spec plus current query rows.
- CLI: version, demo seed, chart add/list/show/remove, serve --port (8000 default).
  JSON errors exit nonzero. API health and charts; React saved-chart gallery and
  empty/loading/error states, /api Vite proxy to 127.0.0.1:8000.
- Tests with temporary dirs: crypto round-trip/permissions, SQL read-only checks,
  Click JSON lifecycle, FastAPI endpoints. CI: locked uv sync, ruff, pytest,
  frozen pnpm install, web build, gitleaks.

## Planned v1: NOT implemented in scaffold

- Link real bank accounts through Plaid Link on the free Trial plan (10 Items).
- Transaction list; recurring/subscriptions via `/transactions/recurring/get`.
- Category budgets, net worth over time using daily balance snapshots.
- In-app bill and low-balance alerts.
- Plaid categories plus user merchant rules; no LLM categorization yet.
- Chat agent pops up charts live; Save pins a chart on the home page.
- Provider setting: local (Ollama), claude, openai. Default local model:
  `hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_M`. Users supply their own keys;
  UI shows the active provider.
- systemd user timer runs `ledgerlight sync` every 6 hours plus daily snapshots.
- Versioned validated charts and no-network sandboxed custom HTML escape hatch.

### v1 acceptance

Use Plaid Sandbox data, never real credentials/account data in automated tests.
Playwright must link/test Sandbox flows, then ask chat for a chart, observe it
pop up live, Save it, and find it again on the home page (including reload).
Verify transaction listing, recurring items, category budgets, daily snapshots,
in-app bill/low-balance alerts and merchant rules with deterministic Sandbox or
synthetic fixtures. Confirm provider selection/active-provider display without
personal keys in tests. Verify token encryption, read-only SQL, no-network HTML
sandbox and loopback binding. These are future acceptance checks, not claims of
passing scaffold features.

## Explicit deferrals

Email/push alerts; Tailscale; SQLCipher; LLM categorization. No Plaid API
or LLM calls, systemd installation, public exposure, GitHub operations or commits
are part of this scaffold task. No empty stub modules for planned features.
