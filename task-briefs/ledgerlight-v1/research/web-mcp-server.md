# Web research: MCP server for ledgerlight (2026-10-03)

Read-only research. Facts below were fetched on 2026-10-03; "UNCERTAIN" marks anything not verified from a primary source.

## 1. Official Python SDK vs FastMCP

| | modelcontextprotocol/python-sdk | FastMCP (now PrefectHQ/fastmcp; jlowin/ URL 301-redirects) |
|---|---|---|
| Stars (GitHub API, 2026-10-03) | 24,475 | 27,965 |
| License | MIT | Apache-2.0 |
| PyPI | `mcp` 2.3.0 (2.x is stable line; Python >=3.10) | `fastmcp` 4.0.10 (Python >=3.10; depends on `fastmcp-slim`; extras `[apps]`, etc.) |
| Spec | v2 speaks 2026-07-28 revision (sessionless, no initialize handshake, no server-initiated requests) and still serves older clients | UNCERTAIN: docs do not state spec version; check before choosing |
| Transports | stdio, Streamable HTTP, SSE | stdio, Streamable HTTP (`http_app()`), SSE |
| Server class | `from mcp.server import MCPServer` (renamed from v1 `FastMCP`) | `from fastmcp import FastMCP` |

Evidence:
- Stars/license: https://api.github.com/repos/modelcontextprotocol/python-sdk and https://api.github.com/repos/PrefectHQ/fastmcp (jlowin/fastmcp returns "Moved Permanently").
- PyPI: https://pypi.org/pypi/mcp/json , https://pypi.org/pypi/fastmcp/json
- Current spec = 2026-07-28 (previous handshake revision 2025-11-25): https://modelcontextprotocol.io/specification/versioning
- SDK v2 notes: https://py.sdk.modelcontextprotocol.io/whats-new/ , migration https://py.sdk.modelcontextprotocol.io/migration/ (raw: https://raw.githubusercontent.com/modelcontextprotocol/python-sdk/main/docs/whats-new.md)
- Note: Roots, Sampling, Logging deprecated in 2026-07-28 (SEP-2577). We need none of them.

### Mounting Streamable HTTP in FastAPI
- FastMCP (documented, with code): `mcp_app = mcp.http_app(path="/")`; `app = FastAPI(lifespan=combine_lifespans(app_lifespan, mcp_app.lifespan))`; `app.mount("/mcp", mcp_app)`. Caveat: omitting the lifespan breaks session manager startup. Avoid top-level CORSMiddleware with OAuth-protected servers. Source: https://gofastmcp.com/integrations/fastapi
- Official SDK: migration guide says the host app's lifespan must enter `mcp.session_manager.run()` because a mounted sub-app's lifespan never runs. Source: https://py.sdk.modelcontextprotocol.io/migration/ . UNCERTAIN: exact v2 method name for getting the ASGI app (v1 used `streamable_http_app()`); the dedicated docs page returned 404, so read https://py.sdk.modelcontextprotocol.io/ "Deployment" before coding.
- Both approaches mount under a path of the existing app, so one uvicorn on 127.0.0.1 serves dashboard + API + `/mcp`. A separate process using stdio (client spawns `ledgerlight mcp`) is the other option and needs no HTTP auth.

### Auth for a localhost server
- Spec: servers SHOULD implement authentication for all connections (Streamable HTTP "Security Warning"). https://modelcontextprotocol.io/specification/2025-11-25/basic/transports
- FastMCP: JWTVerifier/TokenVerifier, simple HTTP bearer, OAuth providers, MultiAuth. https://gofastmcp.com/servers/auth/authentication (the page's "static token" example actually shows JWTVerifier; UNCERTAIN how to do a plain static token, check `StaticTokenVerifier` in docs).
- Official SDK: has a TokenVerifier hook (UNCERTAIN, from memory of v1; not re-verified for v2).
- Simplest option for us: a FastAPI/Starlette middleware (or dependency) on the `/mcp` mount that checks a static `Authorization: Bearer <token>` read from a file in the data dir. Claude Code can send it: `claude mcp add --transport http NAME URL --header "Authorization: Bearer ..."` (https://code.claude.com/docs/en/mcp). stdio transport avoids the token entirely.

## 2. Click CLI -> MCP tools

- Auto-generation libs exist but are tiny:
  - crowecawcaw/click-mcp: `@click_mcp` decorator, nested groups become `users.create`, stdio only, 14 stars, MIT, last push 2026-07-20. https://github.com/crowecawcaw/click-mcp
  - Coding-Dev-Tools/click-to-mcp: wraps any Click/typer CLI, 7 stars, license NOASSERTION. https://github.com/Coding-Dev-Tools/click-to-mcp
  - MladenSU/cli-mcp-server: runs arbitrary shell commands (not Click introspection), 177 stars, last push 2025-07. https://github.com/MladenSU/cli-mcp-server
- No >=1k-star project found that auto-converts Click to MCP (GitHub search "cli to mcp" returns CLIs that ship their own MCP mode, e.g. openclaw/Peekaboo 5,239 stars "macOS CLI & optional MCP server", redhat-et/ripwire 2,389 "CLI + MCP server", CodeGraphContext 4,242). The common real-world pattern is "one core library, two thin front-ends (CLI and MCP)", not auto-generation. UNCERTAIN: search was by GitHub description keywords, so a >=1k project may exist under other wording.
- Auto-generation problems for us: it exposes every command (including writes) with generic schemas, no per-tool annotations (readOnlyHint etc.), no structured output schema, no confirm gating, and subprocess/CliRunner overhead. Our global `--json` already gives stable output, but tool descriptions written for models matter.
- Recommendation: hand-written thin wrappers (`@mcp.tool(annotations=...)`) that call the same Python service functions the Click commands call (not subprocess). If Click commands already contain logic, first move it into a service layer; then both Click and MCP call it. Optionally a test that asserts every read-only Click command has an MCP tool (or is on an explicit exclusion list) to prevent drift. FastMCP can also build from FastAPI routes (`FastMCP.from_fastapi(app)`, operation IDs become tool names), which would reuse the existing API instead of the CLI, but exposes write routes unless filtered.

## 3. MCP Apps (interactive UI in host) and Vega-Lite

- Status: official extension `io.modelcontextprotocol/ui`, spec dated 2026-01-26, package `@modelcontextprotocol/ext-apps` (2,895 stars, license NOASSERTION). Docs: https://modelcontextprotocol.io/extensions/apps/overview ; repo https://github.com/modelcontextprotocol/ext-apps . MCP-UI (https://github.com/MCP-UI-Org/mcp-ui, 5,190 stars, Apache-2.0) is the client-side/renderer framework (`@mcp-ui/client`).
- Mechanism: tool declares `_meta.ui.resourceUri` pointing at a `ui://` HTML resource; host renders it in a sandboxed iframe; app talks to host over postMessage JSON-RPC (can call server tools, update model context). Modes: inline, fullscreen, picture-in-picture.
- CSP: restrictive by default; "if no domains are declared, no external connections are allowed". External scripts need `_meta.ui.csp.resourceDomains`; fetch/XHR needs `connectDomains`. Doc recommends single-file bundling (vite-plugin-singlefile). Source: https://apps.extensions.modelcontextprotocol.io/api/documents/Overview.html (summary came from a small-model fetch; UNCERTAIN on exact field names, verify in ext-apps spec).
- Hosts with support (community matrix, https://modelcontextprotocol.io/extensions/client-matrix): Claude (web), Claude Desktop, VS Code Copilot, Microsoft 365 Copilot, Goose, Postman, MCPJam, ChatGPT, Cursor, Archestra, PostHog Code. NOT listed: Claude Code (terminal), Codex CLI. Claude Code docs page has no MCP Apps mention (https://code.claude.com/docs/en/mcp). Cursor shipping MCP Apps ~March 2026 per a third-party summary (UNCERTAIN).
- Vega-Lite inside the host: yes in principle. Return a `ui://` resource whose HTML bundles vega, vega-lite, vega-embed inline (or CDN domain listed in `resourceDomains`) and receives the spec via tool result (`structuredContent`). No network needed to render if data travels in the spec. Our existing chart HTML/JS can be reused if it is self-contained. Fallback for hosts without Apps (Claude Code, Codex): return the Vega-Lite JSON plus a PNG/SVG image content block rendered server-side, or a link to the dashboard URL.
- FastMCP has `fastmcp[apps]` (Prefab UI, `@mcp.tool(app=True)`) and a "Custom HTML" path; Prefab is pre-1.0 and breaks often, so avoid it: https://gofastmcp.com/apps/overview
- Caveat: Claude Desktop/claude.ai custom remote connectors require a publicly reachable HTTPS URL; a 127.0.0.1 HTTP server is reachable only by local clients. For Claude Desktop use a local stdio entry (launching `uv run ledgerlight mcp`). UNCERTAIN: whether Claude Desktop renders MCP Apps for stdio servers (docs say "Claude Desktop" supports Apps without transport qualifier). With an SSH tunnel, Desktop/Cursor on the remote laptop would need the stdio command to run locally and call the tunneled API, or the tunneled `http://127.0.0.1:PORT/mcp` URL for clients that accept it (Claude Code, Cursor, Codex).

## 4. Elicitation for human confirmation

- Spec (2026-07-28): form mode (flat schema, primitives/enums) and URL mode (out of band, data never reaches client). Delivered via multi-round-trip: server returns `InputRequiredResult` with `elicitation/create`, client retries with `inputResponses`. Actions: accept/decline/cancel. Form mode MUST NOT ask for secrets. https://modelcontextprotocol.io/specification/2026-07-28/client/elicitation
- SDK v2: `Resolve(fn)` + `Elicit(...)` is the preferred way; `ctx.elicit()` still works for legacy-connection clients. https://py.sdk.modelcontextprotocol.io/whats-new/
- Client support (each is a capability the client declares; servers must not send unsupported modes):
  - Claude Code: yes (docs mention an "elicitation dialog") https://code.claude.com/docs/en/mcp
  - Cursor: added in 1.5 (2025-08-21) per third-party summary; a forum thread reports hangs on Windows in 3.10.20 https://forum.cursor.com/t/mcp-elicitation-create-hangs-agent-on-windows-in-cursor-3-10-20-but-works-on-macos/165391
  - Codex CLI: added v0.119.0 (Apr 2026); prompts show in TUI only when approval policy enables `mcp_elicitations`; full-access mode auto-approves https://codex.danielvaughan.com/2026/04/11/codex-cli-mcp-maturation-resource-reads-outputschema/ (third-party blog)
  - Claude Desktop: listed as supporting Elicitation on glama.ai client page (low-quality source) UNCERTAIN
  - ChatGPT: UNCERTAIN, not verified
- Design implication: do NOT rely on elicitation as the only gate. Codex full-access auto-approval and any client that auto-accepts defeat it, and an agent could itself call a "confirm" tool. Keep the settled design: MCP tool creates a proposal row only (no data write); the human clicks Confirm in the web app; MCP has no confirm/apply tool. Elicitation can be an optional courtesy ("proposal #12 created, open dashboard to confirm") or URL-mode elicitation pointing to the proposal page.

## 5. Security guidance

- Spec MUSTs for Streamable HTTP: validate `Origin` header on all connections to stop DNS rebinding (invalid Origin -> 403); local servers SHOULD bind to 127.0.0.1 not 0.0.0.0; SHOULD authenticate all connections. https://modelcontextprotocol.io/specification/2025-11-25/basic/transports
- Official SDK has `TransportSecuritySettings(enable_dns_rebinding_protection, allowed_hosts, allowed_origins)`; the middleware defaults protection OFF when settings are omitted (code comment: "disable ... by default for backwards compatibility"). So set it on explicitly: allowed_hosts like `127.0.0.1:*`, `localhost:*`; allowed_origins like `http://127.0.0.1:*`. https://raw.githubusercontent.com/modelcontextprotocol/python-sdk/main/src/mcp/server/transport_security.py . UNCERTAIN: whether the v2 `MCPServer` applies it automatically when mounted in FastAPI.
- If mounted inside FastAPI under the existing app, our own middleware must also check Host and Origin (and the SSH tunnel keeps Host as 127.0.0.1:PORT on the server side, so strict Host checks still work).
- Tool annotations: `readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint` (+ `title`) under `annotations`. Spec: clients MUST treat annotations as untrusted unless the server is trusted; they are hints, not enforcement. https://modelcontextprotocol.io/specification/2026-07-28/server/tools . Exact defaults (destructiveHint default true, readOnlyHint default false) are from memory of the schema, UNCERTAIN on this fetch.
- Server MUSTs (tools page): validate inputs, access control, rate limit, sanitize outputs. Clients SHOULD show tool inputs and confirm sensitive ops.
- Financial-data specific: tool output goes into the LLM context of an external provider; mark which tools return raw transactions, cap row counts, and consider redaction of account numbers. Treat transaction text (merchant names/memos) as untrusted prompt-injection input; since writes are proposal-only that limits damage.

## New questions for the lead
1. Transport: HTTP mounted in the FastAPI app (one process, needs Host/Origin + bearer token) vs separate stdio command (`ledgerlight mcp`, no HTTP auth, works with Claude Desktop/Cursor/Codex/Claude Code)? Or both?
2. SDK choice: official `mcp` 2.x (MIT, smaller surface, v2 is new so API names changed recently) vs `fastmcp` 4.x (Apache-2.0, documented FastAPI mount + auth providers + Apps, much larger dependency tree)? Needs a short spike to confirm the FastAPI mount for the official SDK v2.
3. Do we want MCP Apps inline charts at all, given Claude Code and Codex CLI do not render them? If yes, plan a fallback (image block / dashboard link). Is the "drive the live dashboard" part better done by pushing state to the web app (WebSocket/SSE) than by the MCP App?
4. Where does tool logic live: confirm Click commands call a shared service layer; if not, that refactor comes first.
5. Is "write" limited to proposals for every tool (including category edits, budget changes)? List which tools are readOnly vs proposal-creating, and whether proposals can be listed/withdrawn by the agent but never confirmed.
