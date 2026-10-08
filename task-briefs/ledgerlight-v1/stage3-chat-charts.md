# Stage 3 — LLM provider setting, chat agent, live charts, Save, HTML sandbox

GOAL: a chat panel where the agent answers money questions and pops up charts
live, Save pins a chart to the home page, the provider is switchable, and custom
HTML charts run in a no-network sandbox.

REPO: personal/ledgerlight (branch `v1-stage3-chat`, from main after stage 2 merged)

Read first: `task-briefs/ledgerlight-v1/decisions.md` (binding),
`task-briefs/ledgerlight-v1/stage2-notes.md` (lead writes it), root/component
`context.md` files and `src/ledgerlight/SKILL.md`.

## Settled design

- Providers: `local` (Ollama HTTP at `OLLAMA_HOST`, default
  `http://127.0.0.1:11434`, model `OLLAMA_MODEL` default
  `hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_M`), `claude` (Anthropic Messages
  API, `ANTHROPIC_API_KEY`, model `LEDGERLIGHT_CLAUDE_MODEL` default
  `claude-sonnet-5-5`), `openai` (`OPENAI_API_KEY`, model
  `LEDGERLIGHT_OPENAI_MODEL` default `gpt-5.5`), plus test-only `fake`. Use
  `httpx` directly (move it from dev to runtime deps); no vendor SDKs.
  Selection: settings table value, overridden by `LEDGERLIGHT_LLM_PROVIDER`.
  Never log or return key values; `/api/llm/status` returns provider, model and
  `key_present: bool`.
- CLI-Anything: the agent's only tool is `ledgerlight` itself. Expose one tool
  `run_ledgerlight(args: list[str])`. The server runs
  `[sys.executable, "-m", "ledgerlight.cli", "--json", *args]` with no shell,
  timeout 30 s, output capped at 64 KiB. Allowlist read commands plus
  `chart preview`: deny `serve`, `plaid exchange`, `plaid sandbox-link`, any
  `remove`, `settings set`, `rules`/`budgets` writes. The system prompt is the
  packaged `SKILL.md`. Max 8 tool turns per message.
- Charts: add `chart preview --title --sql --type` (validates, returns spec +
  rows, saves nothing) and `chart save` from a preview payload; `chart edit
  <id> [--title --sql --type]` bumps version via the existing internal
  save-by-ID. Add `chart history <id>` only if versions are stored; store
  versions in `chart_versions(chart_id, version, title, sql, spec_json,
  created_at)`.
- Custom HTML escape hatch: chart kind `html` with stored HTML; render in
  `<iframe sandbox="allow-scripts" srcdoc=...>` with a CSP meta
  `default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline';
  img-src data:` injected first in the document; data passed by
  `postMessage` from the parent only. No `allow-same-origin`.
- Chat API: POST `/api/chat` `{messages}` streams Server-Sent Events:
  `text` deltas, `tool` (command + short result), `chart` (preview payload),
  `done`, `error`. History lives in the browser only.

## Build

1. `src/ledgerlight/llm.py` providers + fake (the fake returns a scripted
   reply: for "chart"/"spending" prompts it calls `chart preview` on a
   category spending query and answers with text).
2. `src/ledgerlight/agent.py` tool loop, allowlist, limits.
3. Chart preview/save/edit/versions + html kind in `charts.py`, CLI, API.
4. Web: chat drawer available on every page, streaming text, inline chart
   cards rendered live with a Save button, saved charts on Home with edit
   (title/SQL/type) and delete, provider selector in Settings plus an
   active-provider chip in the header ("test mode" badge for fake).
5. Tests: pytest for allowlist (denied commands, shell metacharacters as
   plain args), timeouts, output cap, provider selection precedence, key never
   in responses, versions bump, html CSP injection, SSE event order with fake.
   Playwright (fake provider): open chat, ask for spending by category, chart
   appears live, Save, go Home, chart is there, reload, still there; switch
   provider in Settings and see the chip update; an html chart cannot fetch
   (the test page asserts a `fetch` from inside the iframe fails).
6. Loopback check: a test asserts `serve` binds only 127.0.0.1.
7. Docs: SKILL.md, README (provider setup, Ollama model pull), context.md.

## OUT OF SCOPE

LLM categorization, email/push, Tailscale, SQLCipher, `.github/`. No real LLM
calls in tests.

## DONE WHEN

`bash scripts/check.sh` exits 0 from the repo root.
