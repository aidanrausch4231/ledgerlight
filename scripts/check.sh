#!/usr/bin/env bash
set -euo pipefail
if [[ -z "${HOME:-}" ]]; then
  HOME="$(getent passwd "$(id -u)" | cut -d: -f6)"
  export HOME
fi
# Callers may clear PATH; add common per-user tool dirs only when tools are missing.
if ! command -v uv >/dev/null || ! command -v pnpm >/dev/null || ! command -v node >/dev/null; then
  export PATH="$HOME/.local/bin:$HOME/.local/share/pnpm/bin:${PATH:-/usr/bin:/bin}"
fi
# The orchestrator may supply a private HOME without the provisioned Chromium.
# Preserve explicit overrides and normal local caches; otherwise use the runner
# cache named by LEDGERLIGHT_PLAYWRIGHT_CACHE when it exists.
if [[ -z "${PLAYWRIGHT_BROWSERS_PATH:-}" && ! -d "$HOME/.cache/ms-playwright" \
  && -n "${LEDGERLIGHT_PLAYWRIGHT_CACHE:-}" && -d "${LEDGERLIGHT_PLAYWRIGHT_CACHE}" ]]; then
  export PLAYWRIGHT_BROWSERS_PATH="$LEDGERLIGHT_PLAYWRIGHT_CACHE"
fi
cd "$(dirname "$0")/.."
# This gate is always offline, even when the caller has live-test settings.
unset LEDGERLIGHT_E2E_PLAID PLAID_CLIENT_ID PLAID_SECRET
unset OPENAI_API_KEY ANTHROPIC_API_KEY LEDGERLIGHT_LLM_PROVIDER
unset OLLAMA_HOST OLLAMA_MODEL LEDGERLIGHT_CLAUDE_MODEL LEDGERLIGHT_OPENAI_MODEL
export PLAID_ENV=sandbox
uv sync --locked
uv run ruff check .
uv run pytest -q
cd web
pnpm install --frozen-lockfile
pnpm build && pnpm e2e
