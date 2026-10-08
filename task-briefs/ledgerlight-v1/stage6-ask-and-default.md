# Stage 6 — "ask a question, get graphs" + default home layout + polish

GOAL: the user asks plain questions in chat ("hey what was my coffee spend
like") and the agent answers in one or two tool calls with charts that appear
on screen automatically; the user can save the Home layout as their default and
reset to it with one button.

REPO: personal/ledgerlight (branch `v1-stage6-ask`, from main after stage 5 merged)

Read first: `task-briefs/ledgerlight-v1/decisions.md` (binding),
`task-briefs/ledgerlight-v1/stage4-notes.md`, root/component `context.md`,
`src/ledgerlight/SKILL.md`, `src/ledgerlight/agent.py`,
`src/ledgerlight/agent_tools.py`, `web/src/lib/agentTools.ts`,
`web/src/lib/uiBus.ts`, `src/ledgerlight/dashboard.py`, `src/ledgerlight/charts.py`.

## Evidence (lead, 2026-10-04, local Ollama default model, demo data)

Asked "hey what was my coffee spend like". The agent tried five different CLI
commands, never found data, hit "maximum eight tools" and showed no chart.
A direct "move the Cash flow card, highlight Net worth" request worked.
No new dependencies are approved for this stage.

## Build

1. Spending question command (shared function, CLI `--json`, API mirror, MCP
   read tool `spending_ask`, allowlisted for the agent):
   `ledgerlight --json spending ask TEXT [--months 12]`. Matches TEXT
   case-insensitively against merchant name, transaction name, category, tags
   and notes, with simple synonyms (coffee → coffee, cafe, café, espresso,
   starbucks, dunkin, "coffee co"; keep the synonym table small and in one
   place). Excludes hidden transactions; uses split parts; expenses only.
   Returns `{query, matched_terms, months:[{month,total,count}],
   merchants:[{name,total,count}], total, average_per_month,
   this_month, last_month, transactions:[...last 10], charts:[spec...]}`
   where `charts` holds two ready Vega-Lite specs (monthly bar + top merchants
   bar) built by `charts.build_spec` conventions. No match → empty arrays and
   a `suggestions` list of nearby categories/merchants.
2. Answer cards: a new frontend tool `show_answer({title, summary, charts})`
   that pins an "Answer" panel at the top of the current page (Home: above the
   grid, not a grid card) with the summary text and the charts, marked with the
   magenta agent style, plus buttons **Add to dashboard** (saves the chart via
   the existing chart save path and adds a `chart` card) and **Dismiss**. One
   answer panel at a time; a new answer replaces it.
3. Agent prompting: update the packaged UI guide/SKILL so that for any
   "how much / what was my X spend / show me X" question the agent calls
   `spending ask` once and then `show_answer` with the returned charts and a
   one-to-two-sentence summary with real numbers. Add a fake-provider scripted
   test of exactly that sequence, and a Playwright test: type the coffee
   question, the answer panel with two charts appears, Add to dashboard adds a
   card. Make Enter send the chat message (Shift+Enter = newline).
4. Default Home layout: buttons on Home **Set as default** and **Reset to
   default**. Storage: one `dashboard_default` row (layout JSON, saved_at) via
   an idempotent migration. Set saves the current layout; Reset restores it as
   a new dashboard version (actor user, undoable, Undo chip). When no default
   is saved, Reset restores the built-in seed layout. First-run seeding is
   unchanged. CLI `dashboard default save|reset|show`, API mirror, agent
   frontend tool `reset_home`, MCP tool `dashboard_reset_default`. Tests:
   pytest for save/reset/undo; Playwright: move a card, Set as default, move
   again, Reset → saved layout returns; reload persists.
5. Polish bugs found by the lead:
   a. Undo chip/badge text says "Agent ..." for every non-user actor; use the
      real actor: "CLI moved …", "MCP moved …", "Agent moved …".
   b. The receipt banner stays on unrelated pages after navigation; clear it on
      the next user navigation.
   c. Saved/answer charts use Vega's default blue and are unreadable in dark
      mode (white grid, dark labels); apply Tide Table tokens as a Vega config
      (light and dark), axis labels readable, x-axis labels visible inside the
      card height.
   d. `demo seed` dates are fixed to Jan–Mar 2026, so Home shows $0 this month;
      generate demo transactions relative to today (last ~120 days) and add a
      few coffee-shop merchants (e.g. "Demo Coffee Co", "Bean There Cafe") so the
      coffee question has data. Keep it idempotent and synthetic.
   e. Proposals nav item has no icon; add one in the same inline-SVG style.
6. Docs: SKILL.md, README, context.md.

## OUT OF SCOPE

New LLM providers, model changes, `.github/`, `.env*`, `web/public/`, binary files.

## DONE WHEN

`bash scripts/check.sh` exits 0 from the repo root.
