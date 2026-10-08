import { setPageFilters, useUiBus } from '../lib/uiBus'
import TransactionEditor from './TransactionEditor'
import type { Account, Transaction } from '../lib/types'
import { useData, money } from '../lib/api'
import Feedback from '../components/Feedback'

export default function Transactions() {
  const filters = useUiBus().filters.transactions || {}
  const query = new URLSearchParams(filters).toString()
  const accounts = useData<Account[]>('accounts')
  const rows = useData<Transaction[]>(`transactions?${query}`)
  return <>
    <h1>Transactions</h1>
    <form className="filters" key={query} onSubmit={event => {
      event.preventDefault()
      const params = new URLSearchParams()
      new FormData(event.currentTarget).forEach((value, key) => { if (value) params.set(key, String(value)) })
      setPageFilters('transactions', Object.fromEntries(params))
    }}>
      <label>Account<select name="account" defaultValue={filters.account || ''}><option value="">All accounts</option>{accounts.data?.map(a => <option value={a.id} key={a.id}>{a.name}</option>)}</select></label>
      <label>Since<input type="date" name="since" defaultValue={filters.since || ''} /></label>
      <label>Until<input type="date" name="until" defaultValue={filters.until || ''} /></label>
      <label>Category<input name="category" defaultValue={filters.category || ''} placeholder="Exact category" /></label>
      <label>Search<input name="search" type="search" defaultValue={filters.search || ''} /></label>
      <label>Tag<input name="tag" defaultValue={filters.tag || ''} /></label>
      <label>Limit<input type="number" name="limit" min="1" max="10000" defaultValue={filters.limit || '100'} /></label>
      <button type="submit">Apply filters</button>
    </form>
    <Feedback error={rows.error || accounts.error} loading={!rows.data} />
    {rows.data?.length === 0 && <p>No matching transactions.</p>}
    {!!rows.data?.length && <div className="table-scroll" role="region" aria-label="Transaction results" tabIndex={0}><table>
      <thead><tr><th>Date</th><th>Name</th><th>Category</th><th>Amount</th><th>Extras</th></tr></thead>
      <tbody>{rows.data.map(row => <tr key={row.id} data-ui-id={`txn:${row.id}`}><td>{row.date}</td><td>{row.name} {row.pending && <span className="badge">Pending</span>}</td><td>{row.category}</td><td className="number">{money(row.amount)}</td><td>
        {row.hidden && <span className="badge">Hidden</span>}
        {row.note && <p>Note: {row.note}</p>}{row.tags.length > 0 && <p>Tags: {row.tags.join(', ')}</p>}
        {row.splits.length > 0 && <p>Splits: {row.splits.map(s => `${s.category}: ${money(s.amount)}`).join('; ')}</p>}
        {row.split_cleared_at && <p>Splits cleared after amount changed: {row.split_cleared_at}</p>}
        <TransactionEditor row={row} />
      </td></tr>)}</tbody>
    </table></div>}
  </>
}

