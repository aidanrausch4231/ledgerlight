import type { Card } from '../lib/uiBus'
import type { Chart, Transaction } from '../lib/types'
import { money, useData } from '../lib/api'
import Feedback from './Feedback'
import SavedChart from './SavedChart'

type Spending = { month: string; total_out: number; cumulative: { day: number; this_month: number; last_month: number }[]; top_merchants: { merchant: string; spent: number }[] }
type Flow = { month: string; income: number; spending: number }
type Worth = { date: string; total: number }
type Bill = { id: string; due_date: string; merchant: string; account: string; amount: number }
type Budget = { category: string; spent: number; limit: number; percent: number }
type Goal = { id: number; name: string; progress: number; target_amount: number; percent: number; archived_at: string | null }
type Alert = { id: number; title: string; detail: string; account_id: string | null }
const dollars = (n: number) => `$${money(n)}`

function Lines({ values, previous, label }: { values: number[]; previous?: number[]; label: string }) {
  const all = [...values, ...(previous || [])]
  const max = Math.max(1, ...all), min = Math.min(0, ...all)
  const points = (nums: number[]) => nums.map((v, i) => `${i * 300 / Math.max(1, nums.length - 1)},${112 - (v - min) / (max - min) * 102}`).join(' ')
  return <svg className="tide-chart" viewBox="0 0 300 120" preserveAspectRatio="none" role="img" aria-label={label}>
    <path d="M0 30H300M0 60H300M0 90H300" stroke="var(--rule-soft)" fill="none" />
    {previous && <polyline points={points(previous)} fill="none" stroke="var(--ink-3)" strokeWidth="1.6" strokeDasharray="5 4" />}
    <polygon points={`0,120 ${points(values)} 300,120`} fill="var(--water)" opacity=".6" />
    <polyline points={points(values)} fill="none" stroke={previous ? 'var(--ink)' : 'var(--water-deep)'} strokeWidth="2.4" />
  </svg>
}
function SpendingCard() {
  const result = useData<Spending>('spending/summary')
  if (!result.data) return <Feedback error={result.error} loading={!result.error} />
  const d = result.data, last = d.cumulative.at(-1)?.last_month || 0, delta = d.total_out - last
  return <><p className="sub">Cumulative, all categories · {d.month}</p><div className="figure">{dollars(d.total_out)}</div>
    <p className={delta > 0 ? 'caution' : 'positive'}>{dollars(Math.abs(delta))} {delta > 0 ? 'over' : 'under'} last month’s pace</p>
    <Lines values={d.cumulative.map(v => v.this_month)} previous={d.cumulative.map(v => v.last_month)} label={`Spending: ${dollars(d.total_out)}; last month at the same day: ${dollars(last)}`} />
    <div className="axis"><span>Day 1</span><span>Day {d.cumulative.at(-1)?.day}</span></div>
    <div className="legend"><span>━ This month</span><span>┄ Last month</span></div></>
}
function CashflowCard() {
  const result = useData<Flow[]>('cashflow')
  if (!result.data) return <Feedback error={result.error} loading={!result.error} />
  const rows = result.data, max = Math.max(1, ...rows.flatMap(r => [r.income, r.spending]))
  const net = rows.reduce((sum, r) => sum + r.income - r.spending, 0)
  return <><p className="sub">In and out, last 6 months</p><p className={net >= 0 ? 'positive' : 'caution'}>{dollars(net)} net</p>
    <svg className="tide-chart" viewBox="0 0 300 130" role="img" aria-label={`Six-month cash flow: ${dollars(net)} net`}>
      {rows.map((r, i) => <g key={r.month}><title>{r.month}: In {dollars(r.income)}, Out {dollars(r.spending)}</title>
        <rect x={i * 50 + 8} y={110 - r.income / max * 100} width="14" height={r.income / max * 100} fill="var(--water-deep)" rx="2" />
        <rect x={i * 50 + 25} y={110 - r.spending / max * 100} width="14" height={r.spending / max * 100} fill="var(--ink)" rx="2" />
        <text x={i * 50 + 23} y="128" textAnchor="middle" fill="var(--ink-3)" fontSize="12">{r.month.slice(5)}</text></g>)}
    </svg><div className="legend"><span>▰ In</span><span>▪ Out</span></div></>
}
function WorthCard() {
  const result = useData<Worth[]>('networth?days=365')
  if (!result.data) return <Feedback error={result.error} loading={!result.error} />
  if (!result.data.length) return <p>No balance snapshots yet. Link an account and sync, or seed demo data.</p>
  const rows = result.data
  return <><p className="sub">Recorded balances · last 12 months</p><div className="figure">{dollars(rows.at(-1)!.total)}</div>
    <Lines values={rows.map(r => r.total)} label={`Net worth: ${dollars(rows.at(-1)!.total)}`} />
    <div className="axis"><span>{rows[0].date}</span><span>{rows.at(-1)!.date}</span></div>
    <p className="sub">Debt subtracted. No currency conversion.</p></>
}
function BillsCard() {
  const r = useData<Bill[]>('bills/upcoming')
  return <><p className="sub">Next 30 days</p><Feedback error={r.error} loading={!r.data && !r.error} />
    {r.data?.length === 0 && <p>No upcoming bills.</p>}
    <table className="tide"><tbody>{r.data?.map(b => <tr key={b.id}><td>{b.due_date}<small>{b.account}</small></td><td>{b.merchant}</td><td className="number">{dollars(b.amount)}</td></tr>)}</tbody></table>
    {r.data && <div className="total"><span>{r.data.length} bills</span><b>{dollars(r.data.reduce((s, b) => s + b.amount, 0))}</b></div>}<a href="#/bills">View bills</a></>
}
function BudgetsCard() {
  const r = useData<Budget[]>('budgets/report')
  return <><p className="sub">This month’s category limits</p><Feedback error={r.error} loading={!r.data && !r.error} />
    {r.data?.length === 0 && <p>No budgets yet.</p>}
    <div className="budget-rows">{r.data?.map(b => <div key={b.category} className={b.percent > 100 ? 'caution' : ''}>
      <div className="total"><b>{b.category}</b><span>{dollars(b.spent)} of {dollars(b.limit)}</span></div>
      <progress aria-label={`${b.category} budget`} value={Math.min(100, b.percent)} max="100" />
      {b.percent > 100 && <small>{dollars(b.spent - b.limit)} over</small>}</div>)}</div><a href="#/budgets">Manage budgets</a></>
}
function GoalsCard() {
  const r = useData<Goal[]>('goals'), goals = r.data?.filter(g => !g.archived_at)
  return <><Feedback error={r.error} loading={!r.data && !r.error} />{goals?.length === 0 && <p>No active savings goals.</p>}
    {goals?.map(g => <div className="goal-row" key={g.id}><svg viewBox="0 0 86 86" role="img" aria-label={`${g.name}: ${g.percent.toFixed(0)} percent saved`}>
      <circle cx="43" cy="43" r="36" fill="none" stroke="var(--rule-soft)" strokeWidth="8" />
      <circle cx="43" cy="43" r="36" fill="none" stroke="var(--water-deep)" strokeWidth="8" strokeDasharray={`${Math.min(100, Math.max(0, g.percent)) * 2.262} 226.2`} transform="rotate(-90 43 43)" />
      <text x="43" y="48" textAnchor="middle" fill="var(--ink)">{g.percent.toFixed(0)}%</text></svg>
      <div><b>{g.name}</b><p>{dollars(g.progress)} of {dollars(g.target_amount)}</p></div></div>)}<a href="#/goals">View goals</a></>
}
function AlertsCard() {
  const r = useData<Alert[]>('alerts')
  return <><Feedback error={r.error} loading={!r.data && !r.error} />{r.data?.length === 0 && <p>All quiet. No active alerts.</p>}
    {r.data?.map(a => <div className="notice compact" key={a.id}><b>{a.title}</b><p>{a.detail}</p>{a.account_id && <a href="#/accounts">View account</a>}</div>)}</>
}
function RecentCard() {
  const r = useData<Transaction[]>('transactions?limit=8')
  return <><Feedback error={r.error} loading={!r.data && !r.error} />{r.data?.length === 0 && <p>No transactions yet.</p>}
    <table className="tide"><tbody>{r.data?.map(t => <tr key={t.id} data-ui-id={`txn:${t.id}`}><td>{t.name}<small>{t.date}{t.pending && ' · Pending'}{t.hidden && ' · Hidden'}</small></td><td className="number">{dollars(t.amount)}</td></tr>)}</tbody></table><a href="#/transactions">All transactions</a></>
}
function MerchantsCard() {
  const r = useData<Spending>('spending/summary')
  return <><p className="sub">This month · posted, visible outflows</p><Feedback error={r.error} loading={!r.data && !r.error} />
    {r.data?.top_merchants.length === 0 && <p>No spending this month.</p>}
    <table className="tide"><tbody>{r.data?.top_merchants.map(m => <tr key={m.merchant}><td>{m.merchant}</td><td className="number">{dollars(m.spent)}</td></tr>)}</tbody></table></>
}
function ChartCard({ id }: { id?: number }) {
  const r = useData<Chart[]>('charts'), chart = r.data?.find(c => c.id === id)
  return <><Feedback error={r.error} loading={!r.data && !r.error} />{chart ? <><p className="sub">{chart.title}</p><SavedChart chart={chart} /></> : r.data && <p>Saved chart no longer exists. Remove this card or choose another chart.</p>}</>
}
export default function DashboardCard({ card }: { card: Card }) {
  switch (card.kind) {
    case 'spending_vs_last_month': return <SpendingCard />
    case 'cashflow': return <CashflowCard />
    case 'net_worth': return <WorthCard />
    case 'upcoming_bills': return <BillsCard />
    case 'budgets': return <BudgetsCard />
    case 'goals': return <GoalsCard />
    case 'alerts': return <AlertsCard />
    case 'recent_transactions': return <RecentCard />
    case 'top_merchants': return <MerchantsCard />
    case 'chart': return <ChartCard id={card.props.chart_id} />
    default: return <p>Unknown card kind.</p>
  }
}
