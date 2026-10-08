# CI context

Purpose: quality, offline browser regression and secret-scanning gates on push
and pull_request. Entrypoint: `workflows/ci.yml`. Inputs: checked-out source and
uv/pnpm lockfiles; outputs: Python lint/tests, web build, Playwright and gitleaks
results. Dependencies: GitHub Actions Ubuntu runners, checkout,
astral-sh/setup-uv, pnpm/action-setup, actions/setup-node,
actions/upload-artifact@v4, gitleaks/gitleaks-action. Python 3.12 and Node 22.

The e2e job installs Chromium and runs the built app with temporary synthetic
storage and fakes. On failure it uploads web/test-results and web/playwright-report
(if produced) as playwright-failure-diagnostics with seven-day retention.
Playwright retains failure traces; the default list reporter need not produce
an HTML report. No live Plaid/LLM calls or credentials are needed.

Exact local equivalents from root:

```sh
uv sync --locked
uv run ruff check .
uv run pytest -q
cd web && pnpm install --frozen-lockfile && pnpm build && pnpm e2e
```

Secret/config names: GITHUB_TOKEN for gitleaks action; no Plaid or LLM secrets
needed. Tests set LEDGERLIGHT_DATA_DIR and LEDGERLIGHT_CONFIG_DIR to temporary
paths; never load .env. Gitleaks checkout uses fetch-depth: 0 for full history.
Do not weaken permissions (contents: read), skip scanners or use real bank data.
Gitleaks action may require GITLEAKS_LICENSE for organization-owned repositories;
the repo is personal, public and open source (MIT). Hosted action execution is not a local
smoke check and must be verified by the lead after pushing.

Not yet built: deployment/release workflows, CI-scheduled sync or license checks
(license: MIT).
