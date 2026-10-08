# Stage 3 independent review (headless)

You are the independent REVIEWER. Read-only: never edit, create or delete files
in this repo, never commit, never use git stash. You may run read-only commands and
`bash scripts/check.sh`.

Repo: the current directory (a git worktree). The candidate is the diff
`git diff main...HEAD` (stage 3 commit on top of main).

Review it against `task-briefs/ledgerlight-v1/stage3-ui-dashboard.md` and
`task-briefs/ledgerlight-v1/decisions.md` (including "Harness facts"), and against
the chosen design `design/mockups/CHOSEN.md` + `design/mockups/direction-1-tide-table.html`
+ `design/mockups/tokens-tide-table.md`.

Check:
1. Every Build item is done and tested (card kinds, versions/undo, ui_events,
   SSE replay with `after`, CLI/API commands, uiBus exports, Playwright live tests).
2. Undo restores the exact prior layout; SSE ordering and reconnect replay are correct.
3. The UI follows the Tide Table tokens and layout; no "Move money" action exists.
4. Accessibility basics: keyboard reachable controls, visible focus, 375px no
   horizontal scroll.
5. No secrets or real data; CLI/API share functions; SKILL.md documents new commands.
6. `web/public/fonts/*.ttf` are the official OFL Google Fonts files (license txt
   present) — that is expected.

Output: first line VERIFIED or REFUTED. Then findings ranked by severity with
path:line and the exact fix. REFUTE only for real defects or missing brief items.
