import { StatusSelect } from './Bills'
import { setPageFilters, useUiBus } from '../lib/uiBus'
import type { Stream } from '../lib/types'
import { useData, money } from '../lib/api'
import Feedback from '../components/Feedback'

export default function Recurring() {
  const selected = useUiBus().filters.recurring?.direction || ''
  const rows = useData<Stream[]>(`recurring${selected ? `?direction=${selected}` : ''}`)
  return <><h1>Recurring</h1><label>Direction<select value={selected} onChange={e => setPageFilters('recurring', e.target.value ? { direction: e.target.value } : {})}><option value="">All streams</option><option value="in">Income</option><option value="out">Outgoing</option></select></label><Feedback error={rows.error} loading={!rows.data} />
    {(['in', 'out'] as const).map(direction => <section key={direction}>
      <h2>{direction === 'in' ? 'Income' : 'Outgoing'}</h2>
      {rows.data?.filter(r => r.direction === direction).length === 0 && <p>No recurring items.</p>}
      <ul className="cards">{rows.data?.filter(r => r.direction === direction).map(row => <li key={row.id}>
        <h3>{row.description}</h3><p>{money(row.average_amount)} · {row.frequency}</p>
        <p>Next: {row.predicted_next_date || 'Not predicted'}{!row.is_active && ' · Inactive'}</p>
        <StatusSelect id={row.id} status={row.user_status} />
      </li>)}</ul>
    </section>)}
  </>
}

