# Envelope tokens

World: cash-envelope budgeting on a kraft desk. Coloured envelope stock, folder tabs, rubber stamps and a typed routing slip. Warm and tactile. The agent works in blue stamp ink.

## Color

| Token | Light | Dark | Role |
|---|---|---|---|
| `--desk` / `--desk-2` | `#C29C70` / `#B48D61` | `#1B1510` / `#241C15` | Kraft desk with SVG fibre grain / inactive tabs |
| `--wove` | `#FBFAF6` | `#2B251F` | Folder, white envelopes, notepad drawer |
| `--mint` | `#CBEAD7` | `#1E3B2C` | Spending, savings goal stock |
| `--sky` | `#CCDDF4` | `#1E2D45` | Bills routing slip |
| `--gold` | `#F3C95C` | `#4A3910` | Notice slip, budgets, confirm form |
| `--rose` | `#F4C3BC` | `#4A2629` | Dining (the moved envelope) |
| `--lilac` | `#DAD1F1` | `#2F2946` | Net worth |
| `--on-stock` / `--on-stock-2` | `#2A1C11` / `#4E3B2B` | `#F3EADC` / `#D3C6B4` | Text on any stock |
| `--ink` / `--ink-2` | `#2A1C11` / `#4A3523` | `#F3EADC` / `#D2C3AF` | Text on the desk |
| `--crease` / `--rule` | `rgba(42,28,17,.16)` / `.14` | `rgba(243,234,220,.14)` | Envelope flap crease, rules |
| `--red` | `#A51F1A` | `#FF9C8F` | Red stamp: low balance, over budget, "Needs OK" |
| `--blue` / `--blue-ink` | `#2846B4` / `#FFFFFF` | `#93A9FF` / `#0F1534` | Agent: dashed outline, stamp, Undo stub, notepad rules |
| `--pos` | `#1F6B3F` | `#7FD6A1` | Income, under pace, on track |

Each card is an envelope. `--stock` picks its paper, and a two-gradient V crease draws the flap in the top 26px.

## Type
- Bricolage Grotesque (opsz, wdth, wght) for everything. Display 800 at opsz 96, tracking -0.035em: wordmark 27, h1 30, figures 38. Card title 17 700. Body 15/1.45. Captions 13.5.
- Stamps: Bricolage 800, `wdth 75`, uppercase, tracking .12em, 2.5px border, rotated -4°.
- Courier Prime only for typed data: dates, axis labels, form field labels.
- Tabular lining figures on amounts.

## Spacing, radius, elevation
- Folder padding 24/26. Envelope padding 38 top (flap), 20 sides, 18 bottom. Grid gap 22 (26 mobile, to leave room for stubs).
- Radius: envelopes 8, folder 0/12/12/12 (tab corner square), tabs 10 10 0 0, chips 999, mic 50%.
- Elevation is paper on a desk: `--shadow` = `0 2px 3px` plus `0 10px 22px -12px` in warm brown. A lifted card uses `--lift`. No coloured glows.

## Motion: agent-driven card moves
- Move = pick up and drop. The card lifts (scale 1.04, rotate -5°, larger shadow), travels on a slight arc, and lands at rotate -1.4°: 560ms `cubic-bezier(.16,1,.3,1)` (long ease-out, no bounce).
- On landing, the blue "Moved by agent" stamp presses in: scale 1.3 → 1, opacity 0 → 1, 160ms. The dashed blue outline and the "Moved to top-left · Undo" stub appear.
- After 8s the card settles flat (rotation to 0, outline fades, 600ms). The stamp stays until the next agent action, and the chat keeps the Undo.
- Undo plays the lift and drop in reverse. Highlight is a blue dashed outline with no rotation. Filter: other envelopes slide 6px down and drop to 50% opacity.
- Reduced motion: no lift or arc. The card swaps place, and the stamp and outline appear at once.
