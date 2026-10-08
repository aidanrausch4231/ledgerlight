import { setPageFilters, useUiBus } from '../lib/uiBus'
import { api, money, useAction, useData } from '../lib/api'
import Feedback from '../components/Feedback'

type Bill = { id: string; merchant: string; amount: number; due_date: string; account: string; user_status: string | null }
export function StatusSelect({ id, status }: { id: string; status: string | null }) {
  const action = useAction()
  return <><label>User status<select aria-label={`User status ${id}`} value={status || ''} disabled={action.busy} onChange={e => void action.run(() => api(`recurring/${encodeURIComponent(id)}/mark`, { status: e.target.value || null }))}>
    <option value="">Normal</option><option value="cancel_intent">Cancel intent</option><option value="ignored">Ignored</option>
  </select></label><Feedback error={action.error} loading={false} /></>
}
export default function Bills() {
  const days = Number(useUiBus().filters.bills?.days ?? 30)
  const setDays = (days: number) => setPageFilters('bills', { days: String(days) })
  const rows = useData<Bill[]>(`bills/upcoming?days=${days}`)
  return <><h1>Bills</h1><label>Days ahead<input type="number" min="0" max="36500" value={days} onChange={e => setDays(Number(e.target.value))} /></label>
    <p>Ignored streams are excluded. Cancel intent is a reminder, not a bank cancellation.</p>
    <Feedback error={rows.error} loading={!rows.data} />{rows.data?.length === 0 && <p>No upcoming bills.</p>}
    <ul className="cards">{rows.data?.map(b => <li key={b.id}><h2>{b.merchant}</h2><p>{b.due_date} · {money(b.amount)} · {b.account}</p><StatusSelect id={b.id} status={b.user_status} /></li>)}</ul>
  </>
}
