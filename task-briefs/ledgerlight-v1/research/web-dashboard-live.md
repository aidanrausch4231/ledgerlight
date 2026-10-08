# Web research: dashboard grid, animation, live events, faster-whisper
Date: 2026-10-03. Star counts via `gh api repos/<r>` (GitHub API, read at research time). Versions via npm/PyPI registry JSON.

## Star/license/maintenance table (>=1,000 stars rule)
| Repo | Stars | License | Last push | Latest release |
|---|---|---|---|---|
| react-grid-layout/react-grid-layout | 22,440 | MIT | 2026-09-16 | v2.2.4 (2026-07-29) |
| gridstack/gridstack.js | 9,151 | MIT | 2026-10-01 | v14.0.0 on npm (npm only; GH "latest release" 404) |
| clauderic/dnd-kit | 17,691 | MIT | 2026-09-12 | @dnd-kit/react 0.5.0 (pre-1.0) |
| atlassian/pragmatic-drag-and-drop | 12,782 | NOASSERTION (Apache-2.0 per repo; verify) | 2026-10-03 | - |
| motiondivision/motion | 33,816 | MIT | 2026-10-02 | motion 14.0.0 (2026-09-21) |
| SYSTRAN/faster-whisper | 25,688 | MIT | 2026-10-01 | v1.2.1 (2025-10-31) |
| sysid/sse-starlette | 855 | BSD-3 | 2026-09-28 | v3.5.0 |  <-- FAILS the 1,000-star rule

## 1. Grid
- react-grid-layout v2.2.4 (https://github.com/react-grid-layout/react-grid-layout, README "What's New in v2"): full TypeScript rewrite, hooks API, own types, pluggable compactors, responsive breakpoints with per-breakpoint layouts (`breakpoints`, `onBreakpointChange`), drag handle (`dragConfig.handle`). README support table: v2 needs React 18+. npm peer deps `react >=16.3.0` (so React 19 accepted by peer range; no explicit "tested on 19" claim found).
- Programmatic changes + animation: RGL is controlled (`layout` prop). Change the layout array and items move. Its stock CSS (css/styles.css on master) gives `.react-grid-item { transition: transform/left/top/width/height 200ms ease }`, disabled during drag (`react-draggable-dragging`) and `resizing`. So agent-driven move/resize animates for free via CSS transitions; add/remove does not (no enter/exit animation).
- gridstack 14.0.0: pure TS, no deps, ships React wrapper in-repo (/react). Imperative API (`addWidget`, `update`, `removeWidget`) with animate option; DOM owned by gridstack, which fights React's rendering model. 12-column default, responsive via `columnOpts` breakpoints. Bundle unpackedSize ~2.1 MB npm (includes many builds).
- dnd-kit: @dnd-kit/react 0.5.0 (peer React 18||19) is the new rewrite, pre-1.0; sortable only, no 2D grid-with-resize/collision/compaction. You would hand-build x/y/w/h, resize, compaction. Not recommended for this.
- Others not verified: react-rnd, pragmatic-drag-and-drop (primitive only, no layout engine).
- Recommendation (mine): react-grid-layout v2 with controlled layout. Caveat: last release 2026-07-29, ~10 weeks ago; commits still in Sept. Fallback: gridstack.

## 2. Animation
- motion 14.0.0 (peer React ^18||^19, MIT). Layout animation caveats (https://motion.dev/docs/react-layout-animations): uses transform scale (child distortion; use nested `layout` / `layout="position"`), needs `LayoutGroup` for sibling sync, `layoutScroll` for scrollable parents, blocked during horizontal window resize, docs say nothing about combining with drag.
- Conflict: RGL positions items with CSS transforms and its own CSS transition; a Motion `layout` prop on the same element fights it. Do not put `layout` on RGL items.
- Suggested split: let RGL CSS transition handle move/resize; use Motion only INSIDE the item (inner wrapper) and via `AnimatePresence` for enter/exit (fade/scale) of added/removed cards; keep removed card mounted during exit by delaying removal from `layout`. Highlight pulse on agent-touched card: plain CSS keyframe or Motion `animate`.
- View Transitions API: same-document support Chrome/Edge 111+, Safari 18+, Firefox 144+ (https://developer.chrome.com/docs/web-platform/view-transitions). Needs synchronous DOM update in callback; React 19 has no stable built-in API for this, awkward with `flushSync`. Snapshot-based so it can cross-fade charts and would fight RGL drag. Not recommended here. (React's experimental `<ViewTransition>` not checked.)

## 3. SSE vs WebSocket (reasoning plus sources; the best-practice claim is partly my judgment)
- Traffic is one-way (server->browser layout/agent events); user actions (drag, undo) are ordinary POSTs. SSE fits: auto-reconnect in browser `EventSource`, `Last-Event-ID` resume, plain HTTP, works through SSH `-L` tunnel without special config.
- Library: sse-starlette (https://github.com/sysid/sse-starlette): ping keepalive (`ping=`), client disconnect detection, cooperative shutdown. BUT only 855 stars, fails the 1,000 rule. Alternative: native `StreamingResponse(media_type="text/event-stream")` with own `: ping` comment every ~15 s and `Cache-Control: no-cache`; ~30 lines. Starlette/FastAPI newer versions may ship native SSE helpers: NOT checked.
- Pitfalls: Vite dev proxy may buffer (test it); HTTP/1.1 browsers cap 6 connections per origin (use one stream); `EventSource` cannot send auth headers (fine on localhost, or use cookie/query token); dev server reload and graceful shutdown must close streams. Persist events/seq number in SQLite so reconnect can replay and undo state stays consistent.
- WebSocket only worth it if the agent needs low-latency bidirectional audio streaming; push-to-talk can upload one blob via POST instead.

## 4. faster-whisper (https://github.com/SYSTRAN/faster-whisper)
- Stars 25,688, MIT, pushed 2026-10-01; last tagged release 1.2.1 on 2025-10-31 (11 months; repo active but releases slow).
- CPU speed (README, "Small model on CPU", Intel i7-12700K, 8 threads, a ~13 min audio benchmark per README): faster-whisper fp32 beam5 2m37s; int8 beam5 1m42s (1477 MB RAM). That is roughly 8x realtime for `small` (multilingual), int8. small.en should be similar or slightly faster; NOT benchmarked separately. Push-to-talk clips of 5-15 s should return in about 1-3 s on a similar CPU (extrapolation, unverified on user hardware).
- Install size (x86_64 manylinux wheels, PyPI): ctranslate2 4.8.2 ~39 MB, av 19.0.1 ~35 MB, onnxruntime 1.30.0 ~24 MB, plus tokenizers, huggingface-hub, numpy. About 100+ MB of wheels, no torch needed (the `transformers[torch]` dep is only the `conversion` extra). Model `Systran/faster-whisper-small.en` model.bin = 483.5 MB (fp16), downloaded from Hugging Face on first use.
- Decoding: FFmpeg system install NOT needed. README: audio decoded with PyAV which bundles FFmpeg libs (`av>=11` is a hard dependency). MediaRecorder webm/opus can be passed as a file path or file-like object to `model.transcribe()`; PyAV decodes it and resamples to 16 kHz. I did not run it; opus-in-webm via PyAV is expected to work, test with a real Chrome and a Firefox recording (Firefox gives ogg/opus; Safari gives mp4/aac).
- VAD: `vad_filter=True` uses Silero VAD through onnxruntime (that is why onnxruntime is a dependency).

## Uncertainty
- RGL "React 19 verified" not found in docs; only peer range plus README "React 18+". Must smoke-test (it dropped findDOMNode in v2, so likely fine).
- Motion/RGL coexistence is my inference, not from docs.
- small.en CPU numbers extrapolated from `small`.
- The GitHub-API stars are as of today; Pragmatic DnD license flagged NOASSERTION.

## Questions for the lead
1. Accept RGL v2 (last release 2026-07-29) or prefer gridstack? Need a quick React 19 spike either way.
2. sse-starlette has 855 stars: use native StreamingResponse (my suggestion) or waive the rule?
3. Should add/remove cards animate (needs AnimatePresence + delayed layout removal) or is move/resize enough for v1?
4. Which browsers must push-to-talk support (Firefox ogg, Safari mp4 vs just Chrome webm)?
5. Is the 484 MB model download at first use acceptable, or ship base.en (~140 MB, unverified size)?
