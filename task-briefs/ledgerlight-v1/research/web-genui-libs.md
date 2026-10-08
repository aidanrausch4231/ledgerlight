# Web research: agent-drives-the-frontend libraries (excluding CopilotKit / AG-UI)

Date of all star counts: 2026-10-04 (UTC), from `https://api.github.com/repos/<owner>/<repo>` (field stargazers_count).
Scope: ledgerlight = FastAPI+SQLite backend, React 19/TS/Vite frontend, Vega-Lite; providers Ollama / Anthropic / OpenAI; no vendor cloud.

## Star table (verified)
| Project | Stars | License (API / README) | Last push |
|---|---|---|---|
| assistant-ui/assistant-ui | 12,394 | MIT | 2026-10-04 |
| tambo-ai/tambo | 11,181 | MIT (SDK + backend, per README comparison) | 2026-10-04 |
| vercel/ai (AI SDK) | 27,103 | Apache-2.0 (LICENSE file text; API says NOASSERTION) | 2026-10-03 |
| google/A2UI (redirects to a2ui-project/a2ui) | 16,590 | Apache-2.0 | 2026-10-03 |
| vercel-labs/json-render | 18,486 | Apache-2.0 | 2026-10-02 |
| MCP-UI-Org/mcp-ui (mcp-ui) | 5,190 | Apache-2.0 | 2026-09-16 |
| modelcontextprotocol/ext-apps (MCP Apps) | 2,895 | Apache-2.0 transition from MIT (LICENSE text) | 2026-09-25 |
| thesysdev/openui (successor of crayon; crayon URL redirects here) | 9,971 | MIT | 2026-10-03 |
| alibaba/page-agent | 29,317 | MIT | 2026-09-29 |
| openai/chatkit-js | 1,960 | Apache-2.0 | 2026-07-31 |
| openai/openai-apps-sdk-examples | 2,353 | MIT | 2026-04-15 |
| TanStack/ai | 3,161 | MIT | not checked |
| webmachinelearning/webmcp (spec) | 4,446 | NOASSERTION | not checked |
| MiguelsPizza/WebMCP | 1,102 | NOASSERTION | not checked |
| nanobrowser/nanobrowser | 13,896 | Apache-2.0 | not checked |
Excluded (<1,000 stars): run-llama/chat-ui 593; assistant-ui/tool-ui 779; openai/openai-chatkit-advanced-samples 659; jasonjmcghee/WebMCP 883; assistant-ui/assistant-ui-starter 22.
Not relevant (browser automation from outside, not own-UI): browser-use (117,075), playwright-mcp (37,788), nanobrowser.
Not researched per instructions: CopilotKit, AG-UI (ag-ui-protocol/ag-ui is 16,292 stars, only noted).

## Per-candidate notes

### assistant-ui (strongest fit)
- React/TS chat primitives (Thread, Composer...) plus a tool system. Tools can be frontend (execute in browser, so they can call our own router/dashboard store), backend, human-in-the-loop (approval card), provider. Tool UI: `render` on a toolkit entry shows a React component per tool call (could be a Vega-Lite chart or a confirm card). "Interactables": persistent out-of-thread state the AI can read AND write, bidirectional (matches dashboard cards). Generative UI `present` tool composes a tree from a component vocabulary we ship. Evidence: https://www.assistant-ui.com/docs/tools.md
- Backends: AI SDK, LangGraph, AG-UI/A2A, Google ADK, custom `@assistant-ui/react-data-stream` (data-stream / AI SDK UI-message-stream SSE protocol, so a FastAPI backend can emit it), LocalRuntime (own adapter). README lists Ollama among models. Evidence: README https://github.com/assistant-ui/assistant-ui , https://www.assistant-ui.com/docs/runtimes/custom/data-stream.md
- Self-hostable: yes, the library is client-side; `assistant-cloud` (thread storage) is optional. Also has an unstable WebMCP provider doc.
- Fit: React/TS, shadcn copy-in components; README example is Next.js but works in Vite via LocalRuntime/data-stream (unverified in a Vite build). Maturity: high (YC backed, daily commits). Docs now use a newer "use generative" toolkit API and migrated old makeAssistantTool names: API churn risk.

### tambo (tambo-ai/tambo)
- "Agents that speak your UI": register React components with Zod schemas; agent picks one and streams props. Components can be generative (once) or interactable (persist, updated by agent). Local tools run in the browser. Evidence: https://raw.githubusercontent.com/tambo-ai/tambo/main/README.md
- Includes its own agent backend (conversation loop). Self-host = same backend via Docker, needs Node.js + PostgreSQL. LLMs: OpenAI, Anthropic, Gemini, Mistral, Cerebras, any OpenAI-compatible provider (Ollama exposes that, unverified).
- Fit: second backend service (Node+Postgres) next to FastAPI, and Python tools would sit behind it. That is heavier than we need; conversation state would live in Tambo, not our SQLite. Maturity: 1.0 released, fast moving.

### Vercel AI SDK (vercel/ai)
- Not a UI-driving library by itself: provides streaming protocol, `useChat`, tools with typed tool parts, client-side tool execution (onToolCall / no-execute tools returned from browser), providers incl. Ollama community provider, Anthropic, OpenAI. Gen UI = render tool parts as React components.
- Backend is TypeScript; a Python FastAPI backend can emit the UI message stream protocol (SSE; assistant-ui doc confirms this format is a supported wire protocol). Python-side helpers are third party/unverified.
- Good as the wire protocol and `useChat` layer; pair with assistant-ui or own components. Very mature. Evidence: assistant-ui data-stream doc above. I did not fetch ai-sdk.dev docs (uncertainty).

### Google A2UI (google/A2UI -> a2ui-project/a2ui)
- Declarative JSON UI format; agent sends component tree + data model, client renders from a trusted catalog. Renderers: Flutter, Angular, Lit, React (check). Status "early stage public preview", v0.9.1 production release, v1.0 RC, "expect changes". Evidence: https://raw.githubusercontent.com/google/a2ui/main/README.md
- Describes UI to render, not "navigate/move/resize cards" control; we would still build catalog + actions. Python SDK existence not verified. Fit: possible as card schema but preview maturity.

### vercel-labs/json-render
- Define catalog (Zod) of components and actions; model emits JSON matching schema; progressive streaming render; React, Vue, Svelte, etc.; 36 shadcn components. Self-hostable (pure client library), model-agnostic via AI SDK style. Evidence: https://github.com/vercel-labs/json-render
- Fit: good for "render charts/cards inline" and for a validated "dashboard layout as JSON" idea. Does not provide chat or navigation. Labs product (maturity moderate, 18k stars quickly).

### MCP-UI / MCP Apps (mcp-ui, ext-apps)
- Interactive UI (iframe, HTML) returned by MCP tool servers, rendered by an MCP host/client. Python server SDK exists (mcp-ui-server on PyPI per README badge). Client `@mcp-ui/client` React. Intended to embed third-party sandboxed UI in hosts like Claude/ChatGPT/Goose; not about driving our app's own native components. Overkill; keep as optional later. Evidence: https://github.com/MCP-UI-Org/mcp-ui
- ext-apps: official MCP extension spec for same; 2,895 stars.

### OpenAI Apps SDK / ChatKit
- ChatKit (chatkit-js 1,960 stars, Apache-2.0): embeddable chat widget, but designed to talk to OpenAI-hosted workflows or a ChatKit server; OpenAI-only. Apps SDK examples (2,353) are for apps inside ChatGPT. Reject: vendor-locked, no Ollama/Anthropic.

### Thesys C1 / Crayon / OpenUI
- Crayon repo now redirects to thesysdev/openui (9,971, MIT): "OpenUI Lang" compact UI language plus renderer kit, assistant-ui has an adapter (`@openuidev/assistant-ui`). C1 itself is a hosted API (vendor cloud) so reject C1; OpenUI the open library is plausible but we need own components and weaker models (Ollama) must emit a new DSL: risk. Evidence: assistant-ui tools doc.

### llamaindex chat-ui
- 593 stars: excluded.

### page-agent (alibaba/page-agent, 29,317, MIT)
- In-page DOM GUI agent: one script, LLM reads DOM text, clicks/types. Bring-your-own OpenAI-compatible endpoint (Ollama probably works; unverified). Drives any UI without app changes, but it is brittle/slow for a deterministic dashboard and cannot propose confirm cards. Possible fallback for unplanned UI; not the main design.

### WebMCP (webmachinelearning/webmcp 4,446; MiguelsPizza 1,102)
- Browser API: page registers tools (`document.modelContext`, renamed from navigator.modelContext July 2026) invoked by an agent in the same browser; Chrome 149 origin trial/flags. Not usable for our own in-app chat without flags; assistant-ui has an experimental provider. Evidence: https://zuplo.com/blog/2026/03/13/what-is-webmcp (via search). Watch, do not depend.

### TanStack AI (3,161, MIT)
- Framework-agnostic AI SDK alternative with client tools; not deeply researched. Possible AI SDK alternative.

## Ranking for ledgerlight
1. assistant-ui (+ own FastAPI emitting data-stream/UI-message-stream SSE, LLM calls via our Python provider layer incl. Ollama). Frontend tools = navigate, add/move/resize card, set filter, highlight; tool UI renders Vega-Lite inline; approval card = confirm card for writes; Interactables for card layout state. No second server.
2. json-render (as the inline-render/spec layer inside tool UI: validated JSON for cards/charts) or vercel/ai as protocol layer; json-render wins for "dashboard cards as data", AI SDK is already effectively inside #1.
3. tambo: closest to the "agents speak your UI" description and component-registration model, but brings a Node+Postgres backend; choose only if we want a full agent runtime off the shelf.
Likely "forgotten name" candidates (besides CopilotKit): tambo ("build agents that speak your UI"), assistant-ui, A2UI ("agent-to-user interface"), page-agent.

## Uncertainty
- Stars from live API on 2026-10-04; license of vercel/ai and ext-apps from LICENSE text, not SPDX.
- Did not verify: assistant-ui in a Vite (non-Next) app; Ollama behavior with tool calling reliability (local small models are the main risk for all candidates); Python SDK for A2UI; tambo with Ollama; AI SDK docs directly.
- GitHub API rate limit hit mid-session (only used for a few follow-ups).

## Questions for the lead
- Do we accept TS-only logic for the agent loop (tools declared in frontend) while the LLM loop stays in Python? Recommended: Python runs LLM loop, streams tool-call events; frontend executes UI tools and posts results back.
- Which Ollama models must be supported? Tool-calling quality decides how many tools we can expose.
- Does user want structured JSON layout (json-render style) or imperative tools for card moves?
