# Tide Table tokens

World: a harbour almanac and nautical chart. Calm, airy, editorial. The agent's marks use chart magenta, the colour real charts use for overprinted notices.

## Color

| Token | Light | Dark | Role |
|---|---|---|---|
| `--ground` | `#E4ECE9` | `#071620` | Page (sea-mist chart paper / night chart) |
| `--surface` | `#F6F9F8` | `#0D202B` | Cards, drawer |
| `--panel` | `#D9E6E4` | `#112E3C` | Secondary neutral layer |
| `--ink` | `#0F2A39` | `#D5E6E4` | Primary text, this-month lines, out bars |
| `--ink-2` | `#3D5864` | `#9DB6BA` | Secondary text |
| `--ink-3` | `#55707A` | `#7E989E` | Captions, axes, last-month dashed line |
| `--rule` / `--rule-soft` | `#B8CBCA` / `#D2DFDD` | `#24404D` / `#1A3340` | Hairlines, track fills |
| `--water` | `#C3DCE0` | `#1A4253` | Area fills, active nav, user bubble |
| `--water-deep` | `#3F7F93` | `#6DB0C2` | Income bars, net worth line, budget fill |
| `--overprint` | `#A11F6D` | `#EE7CC0` | Agent only: moved outline, tag, Undo, mic |
| `--overprint-wash` | `rgba(161,31,109,.07)` | `rgba(238,124,192,.09)` | Just-moved card tint |
| `--caution` / `--caution-wash` | `#8F4310` / `#F1E3C4` | `#E9AC62` / `#2E2614` | Low balance, over budget, low water |
| `--pos` | `#1D6A58` | `#74C9AE` | Under pace, gains |

Rule: magenta only marks agent activity. Caution (rust/amber) marks money risk. The two never share a job.

## Type
- Figures and headings: Source Serif 4 (opsz). h1 32/1.1 500; card figures 30/1 500; confirm title 19/1.25 500; almanac sentence 17/1.5 400.
- UI: Schibsted Grotesk. Body 14/1.45; card title 14 600; sub and captions 12.5; minimum 12.
- Tabular figures on amounts only. Schibsted widens punctuation under `tabular-nums`, so keep it off prose.
- Mobile: h1 24, almanac 15.

## Spacing, radius, elevation
- 4px base. Card padding 18/20. Grid gap 18 (16 mobile). Main padding 30/36. Rail 212, collapsed rail 72 below 1180, drawer 384 (340).
- Radius: cards 10, buttons 7, chips and pills 999, notice 8, mobile sheet 16.
- Elevation: 1px hairline borders and a near-flat shadow. Only the just-moved card lifts: `0 12px 24px -16px rgba(5,20,28,.45)`.

## Motion: agent-driven card moves
- Move: FLIP from the old rect to the new one, 600ms `cubic-bezier(.16,1,.3,1)` (long ease-out, like a vessel settling). Other cards reflow over the same curve, 40ms stagger by distance.
- Mark: magenta outline, wash and "Moved here by agent · Undo" tag stay for 8s. Then the outline fades over 1.2s. The chat receipt keeps its Undo.
- Undo plays the same FLIP in reverse and removes the mark immediately.
- Highlight or filter: a magenta 2px ring fades in over 180ms, with a 1.5s dwell. No pulsing.
- `prefers-reduced-motion`: no translation. The card swaps place and the mark appears at once.
