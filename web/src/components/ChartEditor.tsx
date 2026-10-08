import { useState } from 'react'
import { api, fields, useAction } from '../lib/api'
import type { Chart } from '../lib/types'
import { chartInput } from '../lib/chart'
import Feedback from './Feedback'

export default function ChartEditor({ chart }: { chart: Chart }) {
  const action = useAction()
  const [history, setHistory] = useState<{ version: number; title: string; created_at: string }[]>([])
  const input = chartInput(chart)
  return <details className="chart-editor"><summary>Edit chart · version {chart.version}</summary>
    <Feedback error={action.error} loading={false} />
    <form key={chart.version} onSubmit={e => {
      e.preventDefault(); const data = fields(e.currentTarget)
      void action.run(() => api(`charts/${chart.id}/edit`, data))
    }}>
      <label>Chart title<input name="title" defaultValue={input.title} required /></label>
      <label>Read-only SQL<textarea name="sql" defaultValue={input.sql} required /></label>
      <label>Chart type<select name="type" defaultValue={input.type}>{['bar', 'line', 'area', 'arc', 'html'].map(t => <option key={t}>{t}</option>)}</select></label>
      <label>Sandbox HTML<textarea name="html" defaultValue={input.html} /></label>
      <button disabled={action.busy}>Save new version</button>
    </form>
    <button disabled={action.busy} onClick={() => void action.run(async () => setHistory(await api(`charts/${chart.id}/history`)))}>Load chart history</button>
    <ol>{history.map(h => <li key={h.version}>Version {h.version}: {h.title} · {h.created_at}</li>)}</ol>
  </details>
}
