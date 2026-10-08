# ledgerlight v1 — settled decisions (all stages)

Read `specs/project-brief.md`, `context.md` and every component `context.md`
before editing. This file adds the v1 decisions made by the owner and the lead on
2026-10-03. If a stage brief conflicts with this file, the stage brief wins.

## Scope change (agreed)

v1 is the agreed scope change that `AGENTS.md` asks for: Plaid calls, LLM calls,
the systemd unit files and the new dependencies named in the stage briefs are
approved. Stage 1 updates that `AGENTS.md` line to say Plaid/LLM calls go only
through their client modules and tests use fakes or Sandbox.

## Rules for every worker

- Work only in the files your plan task allows. Do not touch `.github/`, `.env`,
  `*.db`, key files or anything under `task-briefs/` except your report.
- Never use `git stash`. Never commit, push or open PRs. The lead integrates.
- Never put real account data, real Plaid tokens or real API keys in code,
  fixtures, tests, logs or reports. Tests use temporary dirs plus synthetic or
  Plaid Sandbox data only.
- No `.env` auto-loading. Read settings from environment variables only.
- Keep the CLI-Anything contract: every new command supports global `--json`,
  JSON errors exit nonzero, and `SKILL.md` documents every new command and its
  JSON output shape.
- Keep the schema idempotent (`CREATE TABLE IF NOT EXISTS`, additive
  `ALTER TABLE` guarded by a column check). Never drop or rewrite user data.
- Keep the server on 127.0.0.1 only.
- Update `context.md` files and `README.md` for what you build. Move items out of
  "not yet built" only when they are built and tested.
- Do not add stub modules for later stages.

## Plaid

- Use `plaid-python` (already a dependency). Env: `PLAID_CLIENT_ID`,
  `PLAID_SECRET`, `PLAID_ENV` (`sandbox` default; also `production`).
- All Plaid access goes through one small client module with an interface the
  tests can replace with a fake (dependency injection or a module-level factory).
  Unit tests and the default Playwright run never touch the network.
- Live Sandbox mode exists for the lead: when `LEDGERLIGHT_E2E_PLAID=sandbox` is
  set, the Playwright Plaid spec creates a public token with
  `/sandbox/public_token/create` (institution `ins_109508`, products
  `["transactions"]`), posts it to the app's exchange endpoint, runs sync, and
  checks transactions and recurring items appear. Without that variable the spec
  uses the fake. Workers may run the live mode only if `PLAID_CLIENT_ID` and
  `PLAID_SECRET` are present; never print their values.
- Production Link UI: the web app ships a "Link account" button using
  `react-plaid-link` with a link token from the API. Tests do not drive Plaid's
  iframe.
- Encrypt access tokens with the existing Fernet helpers before storage.

## Prices (manual accounts and holdings)

- Crypto prices come from the CoinGecko free public API and stock quotes from
  Yahoo's v8 chart endpoint (one request per ticker; Stooq's quote URL now
  returns 404 and Yahoo's v7 batch quote returns 401), both without keys, and only through `src/ledgerlight/price_client.py`.
  Only coin ids, symbols and tickers leave the machine.
- Tests never call price APIs: they use `LEDGERLIGHT_FAKE_PRICES=1` (env only,
  shown as test mode) or a guarded real client with the request method replaced.

## Testing

- Python: pytest with temp `LEDGERLIGHT_DATA_DIR` / `LEDGERLIGHT_CONFIG_DIR`.
- Browser: Playwright (`@playwright/test`) under `web/e2e/`, chromium only,
  started against a real `ledgerlight serve` on a free port with temp data
  dirs and fakes enabled through test-only env vars
  (`LEDGERLIGHT_FAKE_PLAID=1`, and in stage 3 `LEDGERLIGHT_LLM_PROVIDER=fake`).
  Fakes must be impossible to enable by accident in normal use: env var only,
  and the UI shows a visible "test mode" badge when a fake is active.
- Chromium for Playwright is already installed in `~/.cache/ms-playwright`.
- The full local gate, run from the repo root, is `scripts/check.sh`
  (stage 1 creates it): uv sync --locked, ruff, pytest, pnpm install
  --frozen-lockfile, pnpm build, Playwright offline suite. It must set its own
  PATH/HOME defaults because the orchestrator runs it with a cleared environment:
  `export HOME="${HOME:-$(getent passwd "$(id -u)" | cut -d: -f6)}"` and prepend
  `$HOME/.local/bin:$HOME/.local/share/pnpm/bin` (plus the local Node install dir)
  to PATH only when `uv`/`pnpm`/`node` are not already found.
- When you add Python deps run `uv lock`; when you add web deps run `pnpm install`
  so `pnpm-lock.yaml` updates. Lockfiles must match or the gate fails.

## Report

Publish your report artifact with: STATUS / SUMMARY (≤5 bullets) / FILES
(path:line) / CHECKS (exact commands + pass/fail) / OPEN QUESTIONS. If you hit a
decision this brief does not settle, choose the smallest option, finish, and list
it under OPEN QUESTIONS.

## Harness facts (read before reviewing or fixing)

- The orchestrator strips `.env*` files from every worker workspace, so
  `.env.example` ALWAYS looks deleted in `git status`/diffs. That is not a
  change: it is never integrated. Never report it, never try to restore it.
- `task-briefs/` and `design/` may contain untracked files from the lead (later
  stage briefs, mockups). They are inputs, not candidate changes. Never edit,
  delete or report them. Ignore them in reviews.
