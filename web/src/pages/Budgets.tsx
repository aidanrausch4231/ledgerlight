import { setPageFilters, useUiBus } from '../lib/uiBus'
import { api, fields, money, useAction, useData } from '../lib/api'
import Feedback from '../components/Feedback'

type Budget = { category: string; limit: number; spent: number; remaining: number; percent: number }
export default function Budgets() {
  const month = useUiBus().filters.budgets?.month || ''
  const setMonth = (month: string) => setPageFilters('budgets', { month })
  const rows = useData<Budget[]>(`budgets/report${month ? `?month=${month}` : ''}`)
  const action = useAction()
  return <><h1>Budgets</h1>
    <form onSubmit={e => { e.preventDefault(); const f = fields(e.currentTarget); void action.run(() => api('budgets', { category: f.category, monthly_limit: Number(f.limit) })) }}>
      <label>Budget category<input name="category" required /></label>
      <label>Monthly limit<input name="limit" type="number" step="0.01" min="0.01" required /></label>
      <button disabled={action.busy}>Set budget</button>
    </form>
    <label>Report month<input type="month" value={month} onChange={e => setMonth(e.target.value)} /></label>
    <Feedback error={action.error || rows.error} loading={!rows.data} />
    {rows.data?.length === 0 && <p>No budgets yet.</p>}
    <ul className="cards">{rows.data?.map(b => <li key={b.category}><h2>{b.category}</h2>
      <p>Spent {money(b.spent)} of {money(b.limit)} · {b.percent.toFixed(1)}% · Remaining {money(b.remaining)}</p>
      <progress aria-label={`${b.category} progress`} value={Math.min(100, b.percent)} max="100" />
      <button disabled={action.busy} onClick={() => void action.run(() => api(`budgets/${encodeURIComponent(b.category)}/remove`, {}))}>Remove {b.category} budget</button>
    </li>)}</ul>
  </>
}
