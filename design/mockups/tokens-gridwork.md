# Gridwork tokens

World: a visible construction grid (Crouwel-style type-specimen grid) run as an instrument panel. Dense, square, addressable. Every card has a cell address, and agent moves are written as `from → to`.

## Color

| Token | Light | Dark | Role |
|---|---|---|---|
| `--paper` | `#F7F8FB` | `#090B10` | Page under the grid |
| `--cell` | `#FFFFFF` | `#10141C` | Card fill, top bar, log |
| `--grid` | `#D9E0F2` | `#172036` | Construction hairlines, table rules |
| `--grid-2` | `#B4C1E6` | `#27345A` | Rulers, card header rule |
| `--ink` | `#0B0D12` | `#E9ECF4` | Text, bars, primary lines |
| `--ink-2` / `--ink-3` | `#3B4254` / `#5A6275` | `#A6AEC1` / `#8A93A8` | Secondary text / labels, axes |
| `--line` | `#0B0D12` | `#3A4560` | 1px card borders, structural rules |
| `--cobalt` / `--cobalt-ink` | `#1A38D0` / `#FFFFFF` | `#7D93FF` / `#060918` | Agent and primary action: moved card header, ghost, trace, Undo, Confirm |
| `--cobalt-wash` | `#E8ECFC` | `#161E3D` | Hover |
| `--neg` / `--neg-wash` | `#B83F0B` / `#FCEBDF` | `#FF9B5E` / `#2A1A10` | Low balance, over budget, negative month |
| `--pos` | `#0B7449` | `#4FD69B` | Under pace, gains, live sync dot |

## Type
- One family: Archivo, variable width (62–125) and weight.
- Big numerals: 800, `font-stretch:125%`, tracking -0.02em, line-height .95 (sizes 28–40).
- Labels: 12px, 600–800, `font-stretch:75–85%`, uppercase, tracking .04–.08em.
- Body 13/1.4 at `font-stretch:95%`. Table cells 12.5. Minimum 12.
- Tabular figures on all data.

## Spacing, radius, elevation
- Grid: 12 columns × 60px rows (`--row`). Cards inset 4px from cell lines, so each 8px gutter shows the grid line. Mobile: one column with auto rows, grid lines kept as a 25% background.
- Card header strip 30px (6/10 padding). Body padding 9/10. Top bar 48. Log 360 (320 below 1240).
- Radius: 0 everywhere. Square is the system.
- Elevation: flat 1px borders. Only the moved card casts a neutral shadow: `0 14px 30px -18px rgba(10,20,60,.55)`.

## Motion: agent-driven card moves
- Moves snap cell by cell: `steps()` keyframes along the grid route, 520ms total, about 60ms per cell. The card never takes a diagonal.
- During and after the move, a dashed cobalt trace runs along the gutters from the old cell to the new one. A hatched ghost marks the old address. Both stay 6s, then fade over 400ms.
- The moved card's header fills cobalt and the "Moved by agent · Undo" tab docks bottom-right. The log line carries the same address pair and its own Undo.
- Resize grows and shrinks by whole cells, with the address label counting live.
- Highlight: cobalt 2px border, no glow. Filter: non-matching cells drop to 35% opacity in 150ms.
- Reduced motion: the card jumps to its new cell. Ghost and trace still appear, because they carry information.
