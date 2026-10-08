import { api, fields, money, useAction, useData } from '../lib/api'
import Feedback from '../components/Feedback'
import type { Account } from '../lib/types'

type Goal = { id: number; name: string; target_amount: number; target_date: string | null; account_ids: string[]; progress: number; remaining: number; percent: number; on_track: boolean | null; archived_at: string | null }
function GoalForm({ goal }: { goal?: Goal }) {
  const accounts = useData<Account[]>('accounts')
  const action = useAction()
  return <form onSubmit={e => {
    e.preventDefault(); const f = fields(e.currentTarget)
    const account_ids = new FormData(e.currentTarget).getAll('account').map(String)
    void action.run(() => api(goal ? `goals/${goal.id}/update` : 'goals', { name: f.name, target_amount: Number(f.target), target_date: f.date, account_ids }))
  }}>
    <label>Goal name<input name="name" defaultValue={goal?.name} required /></label>
    <label>Target amount<input name="target" type="number" min="0.01" step="0.01" defaultValue={goal?.target_amount} required /></label>
    <label>Target date<input name="date" type="date" defaultValue={goal?.target_date || ''} /></label>
    <fieldset><legend>Linked accounts</legend>{accounts.data?.map(a => <label key={a.id}><input type="checkbox" name="account" value={a.id} defaultChecked={goal?.account_ids.includes(a.id)} />{a.name}</label>)}</fieldset>
    <button disabled={action.busy}>{goal ? 'Update goal' : 'Add goal'}</button>
    <Feedback error={action.error || accounts.error} loading={!accounts.data} />
  </form>
}
export default function Goals() {
  const rows = useData<Goal[]>('goals')
  const action = useAction()
  return <><h1>Goals</h1><p>Tracking only. Linked current balances are summed; no money is moved.</p><GoalForm />
    <Feedback error={action.error || rows.error} loading={!rows.data} />
    {rows.data?.length === 0 && <p>No goals yet.</p>}
    <ul className="cards">{rows.data?.map(g => <li key={g.id}><h2>{g.name}{g.archived_at && ' · Archived'}</h2>
      <p>Progress {money(g.progress)} of {money(g.target_amount)} · {g.percent.toFixed(1)}% · Remaining {money(g.remaining)}</p>
      {g.target_date && <p>Due {g.target_date} · {g.on_track ? 'On track' : 'Behind target'}</p>}
      {!g.archived_at && <><details><summary>Edit goal</summary><GoalForm goal={g} /></details>
        <button disabled={action.busy} onClick={() => void action.run(() => api(`goals/${g.id}/archive`, {}))}>Archive {g.name}</button></>}
    </li>)}</ul>
  </>
}
