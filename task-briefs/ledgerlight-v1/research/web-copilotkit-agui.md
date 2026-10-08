# CopilotKit + AG-UI evaluation for ledgerlight (read-only web research, 2026-10-04)

## Facts (GitHub API, read 2026-10-04 ~01:55 UTC)
- CopilotKit/CopilotKit: 37,726 stars, MIT, last push 2026-10-04, latest v1.77.0 (2026-10-02); v1.76.0 10-01, v1.75.2 09-30 (near-daily releases). ~286 open issues. https://github.com/CopilotKit/CopilotKit
- ag-ui-protocol/ag-ui: 16,292 stars, MIT, last push 2026-10-02, date-tagged releases (release/2026-10-02 ...). ~465 open issues. https://github.com/ag-ui-protocol/ag-ui
- npm: @copilotkit/react-core 1.77.0 (MIT, peer react ^18||^19, zod>=3.25; 7.7 MB unpacked), @ag-ui/client 1.0.1, @ag-ui/core 1.0.1 (MIT). PyPI: ag-ui-protocol 1.0.0 (py>=3.9, only dep pydantic>=2.11.2); copilotkit (python) 0.1.96 pulls langgraph+langchain (NOT wanted).
- Both pass the >=1,000-star bar by a wide margin.

## How it maps to the plan
- AG-UI = SSE event stream (16 event types: RUN_STARTED/FINISHED, TEXT_MESSAGE_*, TOOL_CALL_START/ARGS/END/RESULT, STATE_SNAPSHOT/DELTA, CUSTOM...). Client sends RunAgentInput {messages, tools, state, context, threadId}. https://docs.ag-ui.com/introduction
- Frontend tools: client-defined tools go in RunAgentInput.tools (JSON schema); backend LLM calls them; agent emits TOOL_CALL_* events; browser runs handler and sends result back in next run's messages. https://docs.ag-ui.com/concepts/tools
  - React: `useFrontendTool({name, description, parameters: z.object(..), handler})` from `@copilotkit/react-core/v2`. https://docs.copilotkit.ai/frontend-tools
  - This fits navigate/add/move/resize/remove card/set filter/highlight directly.
- Generative UI: `useComponent` (React component registered as tool, rendered inline in chat), `useRenderTool` (render backend tool calls as cards), state rendering, A2UI, MCP Apps. https://docs.copilotkit.ai/concepts/generative-ui-overview . Vega-Lite inline chart = a component tool taking a spec.
- Human-in-the-loop: `useHumanInTheLoop({name, parameters, render: ({args,status,respond}) => <ConfirmCard onSubmit={respond}/>})` = the confirm-card pattern; LLM calls the tool, UI waits for respond(). https://docs.copilotkit.ai/human-in-the-loop . Second pattern `useInterrupt` is LangGraph interrupt() only. AG-UI protocol itself also has interrupts (RunFinished outcome=interrupt, resume[] in next RunAgentInput). https://docs.ag-ui.com/concepts/interrupts
- Shared state: `useAgent()` -> agent.state reactive, agent.setState(...) pushes UI state to agent; backend sends STATE_SNAPSHOT/STATE_DELTA. https://docs.copilotkit.ai/shared-state (useCoAgent is the v1 name; v2 docs use useAgent.) Could carry "current page, filters, dashboard layout" to the agent each run.

## Python backend / own agent loop / self-host
- Python SDK `ag-ui-protocol` gives pydantic event types + `EventEncoder`; docs show FastAPI `StreamingResponse(media_type="text/event-stream")`. https://docs.ag-ui.com/sdk/python/encoder/overview . So a hand-written agent loop (call LLM, stream tokens, emit TOOL_CALL_* for frontend tools, stop run when a frontend tool is called) is feasible with no LangGraph. Official integrations for LangGraph, Pydantic AI, CrewAI, ADK, Claude Agent SDK etc. exist but are not required. https://github.com/ag-ui-protocol/ag-ui/tree/main/integrations
- No Python "agent loop helper" in the SDK (sdks/python has ag_ui, a2ui_toolkit only): we write the loop, tool-call streaming and the frontend-tool round trip ourselves. This is the main work.
- CRITICAL licensing wrinkle (CopilotKit docs, read via .md pages):
  - Default CopilotKit architecture = React `<CopilotKit runtimeUrl>` -> CopilotKit Runtime (Node/TypeScript server, @copilotkit/runtime, MIT) -> remote AG-UI agent via HttpAgent. TS runtime is "the only runtime that can run without CopilotKit Intelligence"; Python/Go/Ruby/.NET runtimes REQUIRE Intelligence (cloud or self-hosted k8s). https://docs.copilotkit.ai/backend/copilot-runtime . So fully OSS = a Node sidecar in front of our FastAPI. Extra process for a self-hosted Python app.
  - Skipping the runtime: `selfManagedAgents={{id: new HttpAgent({url})}}` on <CopilotKit>. Docs callout says it is "part of CopilotKit's Enterprise Intelligence tier ... licensing for production use". `agents__unsafe_dev_only` is the same shape but "don't ship to production". https://docs.copilotkit.ai/backend/self-managed-agents . Open issue #7015 asks for a runnable self-managed example (no Node runtime): https://github.com/CopilotKit/CopilotKit/issues/7015 . UNCLEAR whether this is technically enforced (license token check) or just a docs/legal statement. Do not rely on it.
  - OSS vs Enterprise page says chat, frontend tools, state, gen-UI and any AG-UI integration need no CopilotKit service; MIT. https://docs.copilotkit.ai/concepts/oss-vs-enterprise
  - publicLicenseKey/Cloud key only for premium features; not needed for OSS. (search snippet, https://docs.copilotkit.ai/premium)
- Cleanest option for us (lead decision): use `@ag-ui/client` (HttpAgent, MIT, 1.1 MB unpacked, AbstractAgent with subscribe() callbacks onToolCallEndEvent, onStateChanged) directly in our React app, with our own thin chat UI and our own tool registry, skipping @copilotkit/react-core. We lose useFrontendTool/useHumanInTheLoop sugar but keep the protocol and Python SDK; ~100 lines of glue. UNVERIFIED: that this works headless without react-core; @copilotkit/react-core also exports `./v2/headless`. https://docs.copilotkit.ai/headless (not read in detail).

## Telemetry
- OSS telemetry is metadata-only (no prompts/messages/state), 5% sample default. Disable: env `COPILOTKIT_TELEMETRY_DISABLED=true` on runtime, or `telemetryDisabled` flag; honours DNT; `COPILOTKIT_TELEMETRY_SAMPLE_RATE`. Inspector (dev builds only) stores a random browser id in localStorage and sends feature-use events directly. https://docs.copilotkit.ai/telemetry
- @copilotkit/react-core has dependency `@scarf/scarf` (npm install-time download analytics; opt out SCARF_ANALYTICS=false). Observed in registry metadata; not checked what it does.
- @ag-ui/client alone: no telemetry observed (not audited).

## LLM providers
- Our own backend does the LLM call, so Ollama/Anthropic/OpenAI are our choice (use native SDKs / OpenAI-compatible Ollama endpoint). Local Qwen via Ollama needs reliable tool calling; that is a model-quality risk, independent of the framework.
- CopilotKit BuiltInAgent (Node, AI-SDK based: OpenAI/Anthropic/Google/any AI-SDK model) is NOT relevant if the agent is Python; the docs warn not to use it if you already have an agent. https://docs.copilotkit.ai/quickstart

## React 19 / Vite / bundle
- react-core peer: react ^18||^19; zod >=3.25 peer. v2 import path `@copilotkit/react-core/v2` plus `/v2/styles.css`. Vite not stated as a problem; quickstarts mostly Next.js. Not tested by me.
- Heavy dependency tree: lit, katex, react-markdown, streamdown, radix, lucide-react, tailwind-merge, tw-animate-css, @tanstack/react-virtual, @jetbrains/websandbox, a2ui-renderer, mcp-apps-renderer, web-inspector, runtime-client-gql (GraphQL, v1 legacy). Tailwind-styled chat UI may clash with our design system. 7.7 MB unpacked is not bundle size; I did not measure gzipped size (no bundlephobia run).

## Gotchas seen (open issues, titles only)
- #6301 v2 message view freezes mid-run in long multi-tool runs; #7494 virtualized thread scroll jump; #6570 frontend tool descriptors arrive in three shapes, wrong one silently yields empty; #6101 pending frontend tool calls on reconnect; #3644 duplicate assistant message IDs with interleaved tool calls; #3206 respond to tool call without followUp; #7539 interrupt+frontend tools; #6408 v1 surfaces orphaned by 1.50 rewrite (v1 vs v2 API churn: docs mix `useCoAgent`/`useCopilotAction` (v1) and `useAgent`/`useFrontendTool` (v2)).
- Fast release cadence (near-daily) = API churn risk; pin versions.
- Multi-step flow: a frontend tool result must be sent back to the LLM in a new run; our Python loop must handle "run ends after frontend tool call, new run continues". Local-model loops may repeat tool calls.

## Does not apply
- LangGraph, CrewAI, ADK, Mastra integrations; BuiltInAgent; Intelligence features (AG-UI Streams, memories, analytics, Slack/Teams channels); Python/Go runtimes (need Intelligence); `copilotkit` PyPI package (drags langgraph/langchain).

## Uncertainty
- Whether `selfManagedAgents` is license-enforced at runtime. Whether @ag-ui/client works without react-core in a Vite app. Gzipped bundle. Exact useFrontendTool/useHumanInTheLoop behaviour with a non-CopilotKit Python backend (should work, since it is just AG-UI tool events; unverified). Doc excerpts partly from a small summarizer; HITL and shared-state facts quoted from docs .md pages directly.

## Questions for lead
1. Accept a Node runtime sidecar (fully OSS, official path) or go headless with @ag-ui/client + own UI (no CopilotKit license ambiguity, less sugar)? Or ask CopilotKit sales whether selfManagedAgents is free for self-hosted personal use?
2. Is a Tailwind/Radix/lucide-heavy chat package acceptable next to our existing UI? Needs a spike to measure bundle.
3. Do we want a spike: FastAPI /agent SSE endpoint with ag-ui-protocol + one frontend tool + one HITL confirm, tested against Qwen3.6 via Ollama?
