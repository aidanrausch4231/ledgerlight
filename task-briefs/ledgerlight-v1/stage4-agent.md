# Stage 4 — providers, AG-UI chat agent that drives the app, confirm cards, push-to-talk, chart edit, HTML sandbox

GOAL: a chat drawer (text + push-to-talk) whose agent answers money questions,
drives the app live through frontend tools, and proposes data changes as Confirm
cards; charts are editable and versioned; custom HTML charts run sandboxed.

REPO: personal/ledgerlight (branch `v1-stage4-agent`, from main after stage 3 merged)

Read first: `task-briefs/ledgerlight-v1/decisions.md` (binding),
`task-briefs/ledgerlight-v1/stage3-notes.md`, root/component `context.md`,
`src/ledgerlight/SKILL.md`. Research evidence (read for API details):
`task-briefs/ledgerlight-v1/research/web-copilotkit-agui.md`.

## Approved dependencies

Python: `ag-ui-protocol` (AG-UI event types + `EventEncoder`), `httpx` moved to
runtime deps, optional extra `voice = ["faster-whisper"]`. Web: `@ag-ui/client`
(and `@ag-ui/core` if needed). NOT `@copilotkit/*`, NOT the `copilotkit` PyPI
package, no LangGraph/LangChain, no vendor LLM SDKs.

## Step 0 — spike (do first, keep it)

Prove in the real app: POST `/api/agent` (AG-UI SSE endpoint) receives
`RunAgentInput` with browser-registered tools, streams `TEXT_MESSAGE_*`,
`TOOL_CALL_*`, `RUN_FINISHED`; the browser `HttpAgent` from `@ag-ui/client`
executes a frontend tool (`ui_navigate`) and the result returns to the loop.
If `@ag-ui/client` cannot run in Vite/React 19, stop and report with evidence.

## Settled design

- Providers: `local` (Ollama `OLLAMA_HOST` default `http://127.0.0.1:11434`,
  `OLLAMA_MODEL` default `hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_M`),
  `claude` (Anthropic Messages API, `ANTHROPIC_API_KEY`,
  `LEDGERLIGHT_CLAUDE_MODEL` default `claude-sonnet-5-5`), `openai`
  (`OPENAI_API_KEY`, `LEDGERLIGHT_OPENAI_MODEL` default `gpt-5.5`), test-only
  `fake`. httpx only. Selection: settings value, overridden by
  `LEDGERLIGHT_LLM_PROVIDER`. `GET /api/llm/status` → provider, model,
  `key_present`. Keys never logged, returned or streamed.
- Agent loop (Python, `src/ledgerlight/agent.py`): system prompt = packaged
  SKILL.md + a short UI guide. Two tool families:
  1. Backend tool `run_ledgerlight(args: list[str])`: runs
     `[sys.executable, "-m", "ledgerlight.cli", "--json", *args]`, no shell,
     30 s timeout, 64 KiB output cap. Allowlist: read commands, `chart preview`,
     and any data-changing command ONLY with `--propose`. Deny `serve`,
     `plaid exchange|sandbox-link`, `settings set` of provider/keys, `mcp`.
  2. Frontend tools registered by the browser and executed by `uiBus`
     (stage 3): `ui_navigate`, `ui_filter`, `ui_highlight`, `dashboard_add`,
     `dashboard_move`, `dashboard_resize`, `dashboard_remove`, `show_chart`
     (inline chart card in chat with Save), `propose_change` (renders a
     Confirm card from a `--propose` payload; Confirm calls
     `POST /api/proposals/<id>/apply`, Cancel discards). Agent-driven
     dashboard changes are recorded with actor `agent` so Undo works.
  Max 8 tool turns per user message.
- `--propose`: every data-changing CLI command from stage 2 accepts
  `--propose`, which stores a `proposals(id, command JSON, summary, created_at,
  applied_at, cancelled_at)` row and returns `{proposal_id, summary, diff}`
  without changing data. Apply re-validates and runs the same function.
- Charts: `chart preview --title --sql --type` (no save), `chart save` from a
  preview, `chart edit <id>` bumping version, `chart history <id>` from
  `chart_versions(chart_id, version, title, sql, spec_json, created_at)`.
- HTML escape hatch: chart kind `html`; render in `<iframe sandbox="allow-scripts"
  srcdoc>` with CSP meta `default-src 'none'; script-src 'unsafe-inline';
  style-src 'unsafe-inline'; img-src data:` injected first; data only via
  `postMessage`; never `allow-same-origin`.
- Push-to-talk: mic button records with MediaRecorder while held (or toggled
  on touch). `POST /api/stt` (multipart audio). Engine: provider `openai` →
  OpenAI transcription API; otherwise local faster-whisper `small.en` int8 CPU
  if the `voice` extra is installed (model downloads on first use; show
  progress state). `GET /api/stt/status` → available engine or none; hide the
  mic when none. Transcript fills the input for the user to send (no
  auto-send). `fake` provider has a fake STT returning fixed text.
- UI: chat drawer on every page in the stage 3 design, streaming text, tool
  activity lines ("Moved card…"), inline chart cards with Save, Confirm cards,
  provider chip in header ("test mode" badge for fake), provider selector in
  Settings.

## Tests

pytest: allowlist (denied commands; shell metacharacters stay literal args;
writes without `--propose` refused), timeout, output cap, provider precedence,
keys absent from all responses/SSE, proposals apply/cancel/re-validate, chart
versions, CSP injection, AG-UI event order with the fake provider, STT status
with/without extra (mock the engine). Playwright (fake provider, fake STT):
ask "move dining vs last month to the top left" → card moves live, Undo
restores; ask for spending by category → chart appears inline → Save → Home
shows it after reload; ask "set dining budget to 400" → Confirm card → Confirm
→ Budgets page shows 400; Cancel path writes nothing; mic button produces the
fake transcript; html chart iframe cannot `fetch`; provider switch updates the
chip; server binds 127.0.0.1 only.

## OUT OF SCOPE

MCP (stage 5), spoken replies, LLM categorization, `.github/`, `.env*`. No real
LLM or STT calls in tests.

## DONE WHEN

`bash scripts/check.sh` exits 0 from the repo root.
