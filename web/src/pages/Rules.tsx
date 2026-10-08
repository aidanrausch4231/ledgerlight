import { useEffect, useState } from 'react'
import { api, useAction, useData } from '../lib/api'
import Feedback from '../components/Feedback'

type Rule = { id: number; pattern: string; category: string; match_field: string; match_type: string; priority: number; match_count: number }
export function RuleForm({ pattern = '', matchField = 'merchant' }: { pattern?: string; matchField?: string }) {
  const [rule, setRule] = useState({ pattern, match_field: matchField, match_type: 'exact', category: '', priority: 100 })
  const [preview, setPreview] = useState<number | null>(null)
  const [previewError, setPreviewError] = useState('')
  const [saved, setSaved] = useState(false)
  const action = useAction()
  useEffect(() => {
    let active = true
    if (!rule.pattern.trim()) return
    api<{ match_count: number }>('rules/preview', { ...rule, category: rule.category || 'Preview' })
      .then(r => { if (active) { setPreview(r.match_count); setPreviewError('') } })
      .catch((e: Error) => { if (active) setPreviewError(e.message) })
    return () => { active = false }
  }, [rule])
  return <form onSubmit={e => { e.preventDefault(); void action.run(async () => { await api('rules', rule); setSaved(true) }) }}>
    <label>Match field<select value={rule.match_field} onChange={e => setRule({ ...rule, match_field: e.target.value })}><option value="merchant">merchant</option><option value="name">name</option></select></label>
    <label>Match type<select value={rule.match_type} onChange={e => setRule({ ...rule, match_type: e.target.value })}><option value="exact">exact</option><option value="contains">contains</option></select></label>
    <label>Pattern<input required value={rule.pattern} onChange={e => setRule({ ...rule, pattern: e.target.value })} /></label>
    <label>Rule category<input required value={rule.category} onChange={e => setRule({ ...rule, category: e.target.value })} /></label>
    <label>Priority<input type="number" step="1" required value={rule.priority} onChange={e => setRule({ ...rule, priority: Number(e.target.value) })} /></label>
    <p>Matching transactions: {rule.pattern.trim() ? preview ?? '…' : 0}</p>
    <button disabled={action.busy}>Add rule</button>
    {saved && <p role="status">Rule saved and applied.</p>}
    <Feedback error={action.error || previewError} loading={false} />
  </form>
}
export default function Rules() {
  const rows = useData<Rule[]>('rules')
  const action = useAction()
  return <><h1>Rules</h1><p>Lowest priority number, then oldest rule wins. Saving/removing re-applies categories.</p><RuleForm />
    <button disabled={action.busy} onClick={() => void action.run(() => api('rules/apply', {}))}>Re-apply rules</button>
    <Feedback error={action.error || rows.error} loading={!rows.data} />
    {rows.data?.length === 0 && <p>No rules yet.</p>}
    <ul className="cards">{rows.data?.map(r => <li key={r.id}>{r.match_field} {r.match_type} “{r.pattern}” → {r.category} · Priority {r.priority} · {r.match_count} matches
      <button disabled={action.busy} onClick={() => void action.run(() => api(`rules/${r.id}/remove`, {}))}>Remove rule {r.id}</button>
    </li>)}</ul>
  </>
}
