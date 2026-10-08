import { api, fields, useAction } from '../lib/api'
import Feedback from '../components/Feedback'
import type { Transaction } from '../lib/types'
import { RuleForm } from './Rules'

export default function TransactionEditor({ row }: { row: Transaction }) {
  const action = useAction()
  const post = (name: string, body: object = {}) => action.run(() => api(`txn/${encodeURIComponent(row.id)}/${name}`, body))
  return <details><summary>Edit transaction</summary>
    <Feedback error={action.error} loading={action.busy} />
    <form onSubmit={e => { e.preventDefault(); void post('note', { note: fields(e.currentTarget).note }) }}>
      <label>Note<input name="note" defaultValue={row.note || ''} /></label><button disabled={action.busy}>Save note</button>
    </form>
    <button disabled={action.busy} onClick={() => void post(row.hidden ? 'unhide' : 'hide')}>{row.hidden ? 'Unhide' : 'Hide'} transaction</button>
    <form onSubmit={e => { e.preventDefault(); void post('tag', { tags: fields(e.currentTarget).tags.split(',').map(t => t.trim()).filter(Boolean) }) }}>
      <label>Tags (comma separated)<input name="tags" required /></label><button disabled={action.busy}>Add tags</button>
    </form>
    {row.tags.map(tag => <button key={tag} disabled={action.busy} onClick={() => void post('untag', { tags: [tag] })}>Remove tag {tag}</button>)}
    <p>Signed split amounts must total {row.amount}. One CATEGORY=AMOUNT per line.</p>
    <form onSubmit={e => {
      e.preventDefault(); const f = fields(e.currentTarget)
      void action.run(async () => {
        const parts = f.parts.split('\n').filter(s => s.trim()).map(s => {
          const index = s.lastIndexOf('=')
          if (index < 1) throw new Error('Use CATEGORY=AMOUNT per line')
          return { category: s.slice(0, index).trim(), amount: s.slice(index + 1).trim() }
        })
        await api(`txn/${encodeURIComponent(row.id)}/split`, { parts })
      })
    }}>
      <label>Split parts<textarea name="parts" required defaultValue={row.splits.map(s => `${s.category}=${s.amount}`).join('\n')} /></label>
      <button disabled={action.busy}>Save split</button>
    </form>
    <button disabled={action.busy} onClick={() => void post('unsplit')}>Remove splits</button>
    <details><summary>Create rule from this</summary><RuleForm pattern={row.merchant || row.name} matchField={row.merchant ? 'merchant' : 'name'} /></details>
  </details>
}
