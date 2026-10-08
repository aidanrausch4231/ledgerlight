# Web context

Manual/holdings: Accounts has **Add manually** (components/ManualForm.tsx) with a
kind picker (loans, cash, other asset, crypto, stock) whose fields change by
kind; crypto debounces GET holdings/search to show the chosen coin before save.
AccountLedger shows holding quantity × price, 24h change, as-of time and a muted
price warning; manual rows show a Manual tag and loan APR/payment. Manual and
holding rows have inline Edit (PATCH) and inline-confirmed Remove (DELETE, no
browser dialog). Refresh prices appears when holdings exist. The ring adds an
Other-assets arc. api() accepts PATCH/DELETE. On phones (<=600px) the Chat
button sits bottom-left so right-aligned balances stay clear, and main has
bottom padding. e2e/serve.py sets LEDGERLIGHT_FAKE_PRICES=1 offline.
Loan rows' Add/Edit form adds "Pays down from transactions matching" and
"Matching since" (date). Edit omits an unchanged since date so a changed match
restarts from the server's today. Loan rows show "Auto-matched: N payments, last
$X on Mon D" or "Matches “TEXT”, no payments yet"; server errors (for example
auto paydown plus a match) show inline. Covered by e2e/loan-match.spec.ts.

Stage 8: Accounts.tsx retains Link/Sync/Relink and polls honest history labels:
full only for completed imports whose oldest date meets the requested span with
14-day tolerance; missing/short history gets a caveat. AccountLedger.tsx and
pages/Accounts.css render GET accounts/overview as a token-colored split ring,
ranked Investments/Cash/Owed ledger with one bar scale, signed owed amounts and
empty-account names. Phone <=600px puts the 104px ring beside net worth, uses
two-line rows and full-width Link below the ledger. Dark colors are live tokens.
useData refreshes on ledgerlight-change; observed background sync status changes
also invalidate overview. Home labels are Add to Home / Add. accounts.spec.ts
covers ordering, ranks, signs, ring accessibility, 390px width, dark tokens,
history caveats/custom depth, event refetch and zero-held track. No binary assets.

Stage 7: Accounts polls GET `/api/sync/status` every two seconds for live Item
counts, oldest dates and import status. Exchange imports automatically. Accounts
carries the original Link token through exchange so the server retrieves the
token's persisted requested depth, even if settings changed while Link was open.
The fake UI uses the same creation/exchange path without loading Plaid. Live
Sandbox token creation requires LEDGERLIGHT_E2E_STORAGE and shares the server's
temporary data/config paths. Default
365-day links show “Importing your last 12 months…” then a date-span-aware label;
custom depths have matching labels. Below-configured-depth Items offer Relink
with explicit confirmation, remote removal then fresh Link, retaining local
transaction annotations. Cancelled Link can be retried from Link account. Paused
30-minute automatic retries show a manual Sync hint; errors remain visible.
Chat stores frontend results but ends successful display-only batches without
another /api/agent request. Mixed/action/failed batches still continue. One 90s
turn timeout aborts the stream, suppresses late callbacks/tools, removes Working
placeholders and offers retry with a fresh HttpAgent conversation (visible entries
remain). Completed UI effects are not rolled back. `year-history.spec.ts` covers
real 60s background completion, oldest-date transaction UI, relink annotations and
a clock-driven timeout/retry; coffee coverage asserts no continuation and Working
gone within 5s. No dependency changes or new binary assets.

Stage 6: `AnswerPanel.tsx` sits above current-page content, outside Home's grid.
`show_answer` validates ready specs and replaces one tab-memory answer; each chart
uses existing save API then adds a chart card, retaining saved ID for failed-pin
retries. Enter sends chat; Shift+Enter stays multiline. Home saves a default or
resets with a user Undo chip; agent reset_home shares the same path. uiBus receipts
and card badges identify CLI/MCP/Agent, and clear on user hash/link navigation
without clearing tool-driven navigation receipts. SavedChart applies CSS Tide Table
tokens to a whitelisted Vega config and responds to theme/system/size changes;
fitted axes keep labels within chart bounds. Proposals now has an inline SVG icon.
Offline ask-default.spec.ts covers the two-call coffee flow, pin/reload,
replacement/dismissal, theme updates and saved default/undo/navigation.

Purpose: responsive local finance UI with a tiny hash router (no router dep).
`src/App.tsx` owns the hash router, Tide Table rail, header alert bell and theme
preference. `src/pages/` owns Home (versioned live cards plus saved Vega gallery),
NetWorth (recorded balance chart), Transactions (filters, note/tag/hide/split editor and create-rule),
Recurring (including user status), Accounts (Link and Sync), Budgets, Rules
(match-count preview), Goals, Bills and Settings. Alerts is available through the bell on every page and inline on Settings;
low-balance notices link to Accounts and never offer money movement. `src/lib/api.ts` centralizes typed
fetch/hooks, mutation invalidation, action errors/loading and formatting;
`src/lib/types.ts` holds shared read shapes, and `src/components/Feedback.tsx`
provides common loading/error display.
`src/tokens.css`: single Tide Table light/dark custom-property source, local
Source Serif 4 / Schibsted Grotesk fonts (OFL notices under public/fonts).
`src/index.css`: shared styling for every page, visible focus, labels, skip link,
scrollable tables, 375px support and reduced-motion behavior. `src/main.tsx` mounts React; Vite proxies /api to loopback.

Data comes only from /api routes; no browser credentials. `react-plaid-link`
loads only after receiving a link token in normal mode; user clicks Continue to
Plaid. Fake mode uses a synthetic exchange, no iframe, and visible test mode
badge from /api/status. Transient tokens remain in memory. Request failures
show alerts, reads show loading/empty states; Vega views finalize on unmount.

Dependencies: Node >=22.12, pnpm 12.4.2, React/TS/Vite/Vega, react-plaid-link,
react-grid-layout v2, Motion, @ag-ui/client/core 1.0.1 and Playwright chromium. From web/: `pnpm install --frozen-lockfile`, `pnpm build`,
`pnpm dev`, `pnpm lint`, `pnpm e2e`, `pnpm e2e:install`. Full root gate:
`bash scripts/check.sh`. The gate falls back to the runner's provisioned Chromium
cache when an isolated HOME has none; PLAYWRIGHT_BROWSERS_PATH overrides win.
Build before starting `uv run ledgerlight serve`.

`playwright.config.ts` allocates a free loopback port shared across workers;
`e2e/serve.py` starts `uv run ledgerlight serve` with temporary data/config and
explicit fake env. Offline spec exchanges through API, syncs and tests pages,
filters, pending markers, chart SVG, mobile width and fake Link/Sync buttons.
Live spec is skipped unless LEDGERLIGHT_E2E_PLAID=sandbox; credentials required,
Sandbox token creation uses the Python client module, no iframe automation.
Screenshots are off; traces are retained only on failure. CI uploads test-results
and any playwright-report for seven days on failure. Default runs use synthetic
data; traces from opt-in live Sandbox may contain tokens and must be treated as
sensitive. Temp storage is cleaned on shutdown.

No VITE_ secrets, `.env` auto-loading, public host or auth support. Built dist
is served by FastAPI from source checkout. Net worth has no FX conversion.
`e2e/money.spec.ts` covers budget progress, rule preview/reclassification, signed
split validation, note/tags/hide, bills, settings/low-balance dismissal and goal
progress/reload. Offline server uses explicit LEDGERLIGHT_TODAY=2026-03-15.
All mutation errors are shown inline. Goal edits/archive, budget/rule removal,
recurring ignore/cancel flags and per-account threshold overrides are supported.
Stage 3: `lib/uiBus.ts` owns one EventSource per tab, snapshot cursor startup,
native Last-Event-ID reconnect, deduplication, page filters, highlights and Undo
receipts. Exports direct UI functions for future stage 4 integration; dashboard
functions persist through the common API. UI undo is tab-local, layout undo is
persisted and version-guarded. New tabs skip old transient UI events. Stable IDs:
page:PAGE, nav:PAGE, card:ID, txn:ID and dashboard. Filters supported on
Transactions, Recurring, Bills and Budgets; UI clear resets them and all marks.
Home uses controlled RGL v2, a gap-preserving collision compactor, CSS move/resize
transitions and Motion AnimatePresence only inside card items. Removed wrappers
stay for the short exit fade. Mobile stacks without saving responsive geometry;
keyboard move/resize forms remain available. Built-in cards read stage 2 API
queries; chart cards validate saved chart IDs and show deleted-chart state.
`components/DashboardCard.tsx` owns card content and `SavedChart.tsx` owns Vega
cleanup. Magenta agent marks last eight seconds; highlight is a two-second,
non-pulsing ring. Reduced motion disables translations/fades. User changes have
no agent receipt. Stale layout receipts fail safely.

`e2e/dashboard.spec.ts` invokes actual CLI commands using the server's temporary
LEDGERLIGHT_E2E_STORAGE path, tests live DOM updates/undo/filters/highlights,
one stream, pointer drag/reload, keyboard controls, system/dark theme and all
pages at 375px. Pointer tests await both SSE coordinates and handle actionability
before dragging, including same-column moves from a distant row, rather than
assuming a fixed animation delay also guarantees event delivery. The server cleans shared temp storage on exit. Fake Plaid or
explicit LEDGERLIGHT_LLM_PROVIDER=fake shows test mode.

Stage 4: `components/Chat.tsx` is an app-owned drawer on every page. HttpAgent
streams text, collects completed frontend calls, dispatches `lib/agentTools.ts`
and returns tool results in continuation runs for action/mixed/failed batches;
successful display-only batches end immediately. The registry uses uiBus with
actor agent; backend run_ledgerlight results are never executed in the browser.
Provider chip/Settings selector use status/provider routes; environment override
is explicit in Settings. The provider selector is controlled, waits for initial
status, and retains user edits across asynchronous status refreshes rather than
remounting on provider changes. Status read failures are shown inline.
Model/key configuration remains on the server.
ConfirmCard fetches the stored proposal rather than displaying an untrusted
model description; only user buttons apply/cancel. Financial reads refresh via
ledgerlight-change. Chat history is in memory and is lost on reload.

`SavedChart.tsx` limits Vega to simple local-data marks/field encodings;
`lib/chart.ts` owns shared chart payload/CSP helpers. HTML
uses a fresh CSP-first srcdoc, sandbox allow-scripts only, opaque origin and
postMessage rows. No HTML is inserted in the parent. `ChartEditor.tsx` edits
saved chart SQL/title/type/markup with server validation and version history.
Inline chat Save is a user action keeping the preview in Home's gallery.
`VoiceInput.tsx` uses MediaRecorder, permission/error handling, held mouse/key or
toggled touch capture, 60-second stop and stream cleanup. STT fills the textarea,
never auto-sends; mic is hidden if the server lacks an engine. Preparation state
explains the optional first-use CPU model download.

Retained `e2e/agent-spike.spec.ts` proves HttpAgent works in Vite/React 19 without
CopilotKit or a Node sidecar and returns browser tool results. `agent.spec.ts`
covers move/Undo, preview/Save/reload/edit/history, Confirm/Cancel, real recorder
with Chromium's fake device + fake STT, CSP fetch denial/opaque parent boundary,
375px drawer and provider switch/persistence on a separate temporary real server.
The provider regression has a 120s test budget and a 60s health poll with bounded
fetches for its separate cold server. It gates all real status responses, waits
for saved Claude data rather than two intercepted requests, and makes the next
unsaved selection before releasing the gate in finally. It then waits for both
the header and Settings model display to refresh before checking the selection,
so a slower Settings read cannot escape the race assertion. Switch/save/reload
checks remain against the real server. Local stress command:
`pnpm exec playwright test e2e/agent.spec.ts -g "saved provider" --repeat-each=10`.
No live provider/model quality claims. Deferred: spoken replies and LLM
categorization.

Stage 5: `pages/Proposals.tsx` and hash routes `#/proposals`,
`#/proposals/<id>` expose pending and individual stored changes. ConfirmCard is
shared with chat and displays only server-fetched summaries/diffs before enabling
Confirm/Cancel. Loading/missing/error/resolved states survive reload. The uiBus
event actor union includes mcp, handled like other non-user SSE activity.
`src/mcp/chart.js` is the minimal MCP Apps JSON-RPC bridge with a safe local-data
Vega renderer. `pnpm build:mcp` (also run by build) bundles it with Vega/Lite/Embed
into packaged Python `resources/chart.html` through scripts/build-mcp-chart.mjs.
No external URLs/assets or network permissions; local compilation uses eval in
the host sandbox. HTML charts are only rendered by the existing web viewer.
`e2e/mcp_client.py` uses an in-process FastMCP client against the browser's temp
storage; `e2e/mcp.spec.ts` verifies live dashboard_move without reload, proposal
list/deep links/Confirm/Cancel/reload/missing states, Apps handshake/rendering and
network/parent denial. Real vendor MCP Apps hosts remain untested.

Duplicate links: Accounts sends Plaid Link metadata (institution id/name and
account name/mask/type/subtype) with the exchange POST. A duplicate returns HTTP
409 and its server message ("<Bank> is already linked (<Account> ••<mask>).
Remove the old link first if you want to link it again.") shows in the existing
alert. Covered by `e2e/duplicate-link.spec.ts`.
