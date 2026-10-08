# Chosen design: Tide Table (owner, 2026-10-03)

Build to `design/mockups/direction-1-tide-table.html` (layout, components, copy tone)
and `design/mockups/tokens-tide-table.md` (color tokens light+dark, type scale,
spacing, radius, motion). Screenshots: `design/mockups/shots/d1-*.png`.

Adjustments:
- Remove the "Move $1,500 from Savings" action from the low-balance alert. ledgerlight
  never moves money; the alert links to the account instead.
- Agent-touched elements use the direction's magenta "notice" color, plus the
  "Moved here by agent · Undo" tag shown on the moved card.
- Ignore the other two directions.
