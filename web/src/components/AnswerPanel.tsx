import { useState } from 'react'
import { api, useAction } from '../lib/api'
import { add, showAnswer, useUiBus } from '../lib/uiBus'
import { chartInput } from '../lib/chart'
import type { Chart } from '../lib/types'
import SavedChart from './SavedChart'

function AnswerChart({ chart }: { chart: Chart }) {
  const action = useAction()
  const [savedId, setSavedId] = useState<number | null>(null)
  const [added, setAdded] = useState(false)
  return <section aria-label={chart.title}><h3>{chart.title}</h3><SavedChart chart={chart} />
    <button disabled={action.busy || added} onClick={() => void action.run(async () => {
      const id = savedId ?? (await api<Chart>('charts/save', chartInput(chart))).id
      setSavedId(id)
      await add('chart', { chart_id: id }, 'user')
      setAdded(true)
    })}>{added ? 'Added to dashboard' : 'Add to dashboard'}</button>
    {action.error && <p role="alert">{action.error}</p>}
  </section>
}

export default function AnswerPanel() {
  const { answer, answerVersion } = useUiBus()
  if (!answer) return null
  return <section className="answer-panel" aria-label="Answer">
    <header className="actions"><span className="badge">Agent answer</span><h2>{answer.title}</h2><button className="quiet" onClick={() => showAnswer(null)}>Dismiss</button></header>
    <p>{answer.summary}</p>
    <div className="answer-charts">{answer.charts.map((chart, i) => <AnswerChart key={`${answerVersion}-${i}`} chart={chart} />)}</div>
  </section>
}
