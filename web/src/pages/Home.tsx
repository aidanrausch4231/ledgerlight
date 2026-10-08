import { useEffect, useState } from 'react'
import GridLayout, { collides, useContainerWidth, type Compactor, type Layout, type LayoutItem } from 'react-grid-layout'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import DashboardCard from '../components/DashboardCard'
import SavedChart from '../components/SavedChart'
import ChartEditor from '../components/ChartEditor'
import Feedback from '../components/Feedback'
import { api, fields, useAction, useData } from '../lib/api'
import { add, dashboardCommand, titles, undo, resetHome, useUiBus, type Card } from '../lib/uiBus'
import type { Chart } from '../lib/types'

// RGL extension: preserve intentional gaps but settle secondary collisions.
// Unlike verticalCompactor, this never pulls a CLI-positioned card upward.
const spacedCompactor: Compactor = {
  type: 'vertical', allowOverlap: false,
  compact(layout) {
    const copy = layout.map(item => ({ ...item }))
    const placed: LayoutItem[] = []
    for (const item of [...copy].sort((a, b) => a.y - b.y || a.x - b.x || a.i.localeCompare(b.i))) {
      let collisions = placed.filter(other => collides(item, other))
      while (collisions.length) {
        item.y = Math.max(...collisions.map(other => other.y + other.h))
        collisions = placed.filter(other => collides(item, other))
      }
      item.moved = false
      placed.push(item)
    }
    return copy
  },
}

export default function Home() {
  const bus = useUiBus(), action = useAction()
  const charts = useData<Chart[]>('charts')
  const { width, containerRef, mounted } = useContainerWidth()
  const reduced = useReducedMotion()
  const cards = bus.dashboard?.cards
  const [retained, setRetained] = useState<{ source: Card[] | undefined; cards: Card[] }>({ source: cards, cards: cards || [] })
  const [defaultSaved, setDefaultSaved] = useState(false)
  const [kind, setKind] = useState('spending_vs_last_month')
  // Retain removed wrappers until AnimatePresence finishes the inner exit.
  if (cards && retained.source !== cards) {
    setRetained({ source: cards, cards: [...cards, ...retained.cards.filter(c => !cards.some(n => n.id === c.id))] })
  }
  const displayed = retained.cards
  const mobile = width < 640
  const markedCard = cards?.find(c => c.id === bus.marked)
  useEffect(() => {
    if (!cards) return
    const timer = setTimeout(() => setRetained({ source: cards, cards }), reduced ? 0 : 220)
    return () => clearTimeout(timer)
  }, [cards, reduced])
  const layout = displayed.map((c, i) => ({ i: c.id, x: mobile ? 0 : c.x, y: mobile ? i * 6 : c.y, w: mobile ? 1 : c.w, h: mobile ? 6 : c.h, minH: 2, maxH: 30 }))
  const persist = (next: Layout) => {
    if (mobile || !bus.dashboard) return
    void action.run(() => dashboardCommand('layout', {
      expected_version: bus.dashboard!.version,
      layout: next.filter(l => cards?.some(c => c.id === l.i)).map(l => ({ id: l.i, x: l.x, y: l.y, w: l.w, h: l.h })),
    }, 'user'))
  }
  return <>
    <div className="page-heading"><div><h1>Home</h1><p className="almanac">Your money, at a glance. A little perspective for the day ahead.</p></div></div>
    <div className="dashboard-tools">
      <form className="actions" onSubmit={e => {
        e.preventDefault(); const f = fields(e.currentTarget)
        void action.run(() => add(kind, kind === 'chart' ? { chart_id: Number(f.chart_id) } : {}, 'user'))
      }}>
        <label>Add to Home<select value={kind} onChange={e => setKind(e.target.value)}>{Object.entries(titles).map(([key, title]) => <option key={key} value={key}>{title}</option>)}</select></label>
        {kind === 'chart' && <label>Saved chart<select name="chart_id" required><option value="">Choose chart</option>{charts.data?.map(c => <option key={c.id} value={c.id}>{c.title}</option>)}</select></label>}
        <button disabled={action.busy}>Add</button>
      </form>
      <button className="quiet" disabled={action.busy || !bus.dashboard} onClick={() => void action.run(async () => { await api('dashboard/default/save', { expected_version: bus.dashboard!.version }); setDefaultSaved(true) })}>Set as default</button>
      <button className="quiet" disabled={action.busy || !bus.dashboard} onClick={() => void action.run(() => resetHome('user'))}>Reset to default</button>
      {defaultSaved && <span role="status">Default layout saved</span>}
      <button className="quiet" disabled={action.busy || !bus.dashboard || bus.dashboard.version <= 1} onClick={() => void action.run(undo)}>Undo layout</button>
    </div>
    <p className="sub">Drag a card by its handle; resize from the lower-right corner. Card controls offer keyboard alternatives.</p>
    <Feedback error={action.error} loading={!bus.dashboard} />
    {cards?.length === 0 && <p>Your dashboard is empty. Add a card above.</p>}
    <div ref={containerRef} data-ui-id="dashboard" aria-label="Dashboard">
      {mounted && <GridLayout width={width} layout={layout} compactor={spacedCompactor}
        gridConfig={{ cols: mobile ? 1 : 12, rowHeight: 48, margin: [mobile ? 16 : 18, mobile ? 16 : 18], containerPadding: [0, 8] }}
        dragConfig={{ enabled: !mobile && !action.busy, handle: '.drag-handle' }}
        resizeConfig={{ enabled: !mobile && !action.busy, handles: ['se'] }}
        onDragStop={persist} onResizeStop={persist}>
        {displayed.map(card => <div key={card.id} data-ui-id={`card:${card.id}`} data-card-id={card.id}
          data-x={card.x} data-y={card.y} data-w={card.w} data-h={card.h}
          style={{ transitionDelay: markedCard && !reduced ? `${Math.min(8, Math.round(Math.hypot(card.x - markedCard.x, card.y - markedCard.y))) * 40}ms` : '0ms' }}
          className={`dashboard-item ${bus.marked === card.id ? 'agent-marked' : ''}`}>
          <AnimatePresence>{cards?.some(c => c.id === card.id) && <motion.section key={card.id} className="dashboard-card" aria-label={titles[card.kind]}
            initial={{ opacity: reduced ? 1 : 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: reduced ? 0 : 0.2 }}>
            {bus.marked === card.id && <div className="overprint">{bus.receipt?.text || 'Layout changed'} · <button onClick={() => void action.run(() => dashboardCommand('undo', { expected_version: bus.markedVersion }, 'user'))}>Undo</button></div>}
            <div className="card-heading"><h2>{titles[card.kind]}</h2><button className="drag-handle quiet" aria-label={`Drag ${titles[card.kind]}`} title="Drag to move; use Card controls for keyboard editing">⠿</button></div>
            <div className="card-body"><DashboardCard card={card} />
              <details className="card-controls"><summary>Card controls</summary>
                <form onSubmit={e => { e.preventDefault(); const f = fields(e.currentTarget); void action.run(() => dashboardCommand('move', { id: card.id, x: Number(f.x), y: Number(f.y) }, 'user')) }}>
                  <label>Column<input name="x" type="number" min="0" max={12 - card.w} defaultValue={card.x} key={`x${card.x}`} required /></label>
                  <label>Row<input name="y" type="number" min="0" max="100000" defaultValue={card.y} key={`y${card.y}`} required /></label><button disabled={action.busy}>Move card</button>
                </form>
                <form onSubmit={e => { e.preventDefault(); const f = fields(e.currentTarget); void action.run(() => dashboardCommand('resize', { id: card.id, w: Number(f.w), h: Number(f.h) }, 'user')) }}>
                  <label>Width<input name="w" type="number" min="1" max={12 - card.x} defaultValue={card.w} key={`w${card.w}`} required /></label>
                  <label>Height<input name="h" type="number" min="2" max="30" defaultValue={card.h} key={`h${card.h}`} required /></label><button disabled={action.busy}>Resize card</button>
                </form>
                <button className="quiet" disabled={action.busy} onClick={() => void action.run(() => dashboardCommand('remove', { id: card.id }, 'user'))}>Remove card</button>
              </details>
            </div>
          </motion.section>}</AnimatePresence>
        </div>)}
      </GridLayout>}
    </div>
    <section aria-label="Saved charts"><h2>Saved charts</h2><Feedback error={charts.error} loading={!charts.data} />
      {charts.data?.length === 0 && <p>No saved charts yet. Create one with <code>ledgerlight chart add</code>.</p>}
      {charts.data?.map(chart => <section key={chart.id} aria-label={chart.title}><h3>{chart.title}</h3><SavedChart chart={chart} /><ChartEditor chart={chart} />
        <button disabled={action.busy} onClick={() => void action.run(() => add('chart', { chart_id: chart.id }, 'user'))}>Pin {chart.title}</button></section>)}
    </section>
  </>
}
