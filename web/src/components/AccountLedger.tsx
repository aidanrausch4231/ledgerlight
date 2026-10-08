import type { CSSProperties, ReactNode } from 'react'
import type { AccountsOverview, OverviewAccount } from '../lib/types'

const dollars = (value: number) => `${value < 0 ? '−' : ''}$${Math.abs(value).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
const percent = (value: number) => `${Math.round(value * 100)}%`
const mask = (value: string | null) => value ? ` ••${value}` : ''
const short = (value: number) => `$${value.toLocaleString('en-US', { minimumFractionDigits: Number.isInteger(value) ? 0 : 2, maximumFractionDigits: 2 })}`
const day = (value: string) => new Date(`${value}T00:00:00`).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
const asOf = (value: string) => new Date(value).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })

function details(a: OverviewAccount) {
  if (a.source === 'holding') {
    const change = a.price_change_24h
    return <>
      <span className="account-holding">{(a.quantity ?? 0).toLocaleString('en-US', { maximumFractionDigits: 8 })} {a.symbol} × {a.price == null ? 'price pending' : dollars(a.price)}</span>
      {change != null && <span className={change < 0 ? 'account-change down' : 'account-change'}>{change < 0 ? '−' : '+'}{Math.abs(change).toFixed(2)}% 24h</span>}
      {a.price_as_of && <span>as of {asOf(a.price_as_of)}</span>}
      {a.price_error && <span className="account-price-error">Price not updated: {a.price_error}</span>}
    </>
  }
  if (a.source === 'manual') return <>
    <span className="account-tag">Manual</span>
    {a.apr != null && <span>{a.apr}% APR</span>}
    {a.monthly_payment != null && <span>{dollars(a.monthly_payment)}/mo{a.payment_day ? ` on day ${a.payment_day}` : ''}</span>}
    {a.auto_paydown && <span>auto paydown</span>}
    {a.payment_match && <span className="account-matched">{a.payments_applied
      ? `Auto-matched: ${a.payments_applied} payment${a.payments_applied === 1 ? '' : 's'}${a.last_payment ? `, last ${short(a.last_payment.amount)} on ${day(a.last_payment.date)}` : ''}`
      : `Matches “${a.payment_match}”, no payments yet`}</span>}
  </>
  return null
}

export default function AccountLedger({ overview: o, actions }: { overview: AccountsOverview; actions?: (account: OverviewAccount) => ReactNode }) {
  const other = o.other_share ?? 0
  return <>
    <section className="account-worth" aria-label="Net worth">
      <svg className="account-ring" viewBox="0 0 42 42" role="img" aria-label={`Holdings: ${percent(o.cash_share)} cash, ${percent(o.invested_share)} invested; owed ${dollars(o.owed)}, ${percent(o.owed_ratio)} of held (capped at 100%)${other ? `; other assets ${percent(other)}` : ''}`}>
        <circle cx="21" cy="21" r="15.915" fill="none" stroke="var(--rule-soft)" strokeWidth="5" />
        {o.held !== 0 && <>
          <circle cx="21" cy="21" r="15.915" pathLength="100" fill="none" stroke="var(--water-deep)" strokeWidth="5" strokeDasharray={`${o.cash_share * 100} ${100 - o.cash_share * 100}`} strokeDashoffset="25" />
          <circle cx="21" cy="21" r="15.915" pathLength="100" fill="none" stroke="var(--ink)" strokeWidth="5" strokeDasharray={`${o.invested_share * 100} ${100 - o.invested_share * 100}`} strokeDashoffset={25 - o.cash_share * 100} />
          {other > 0 && <circle className="other-arc" cx="21" cy="21" r="15.915" pathLength="100" fill="none" strokeWidth="5" strokeDasharray={`${other * 100} ${100 - other * 100}`} strokeDashoffset={25 - (o.cash_share + o.invested_share) * 100} />}
          <circle cx="21" cy="21" r="10.5" pathLength="100" fill="none" stroke="var(--caution)" strokeWidth="2" strokeDasharray={`${o.owed_ratio * 100} ${100 - o.owed_ratio * 100}`} strokeDashoffset="25" />
        </>}
      </svg>
      <div className="account-worth-copy">
        <div className="account-eyebrow">Net worth</div>
        <div className="account-worth-number">{dollars(o.net_worth)}</div>
        <div className="account-legend">
          <span><i className="cash-dot" />Cash <span className="legend-amount">{dollars(o.cash_total)} · </span>{percent(o.cash_share)}</span>
          <span><i className="invested-dot" />Invested <span className="legend-amount">{dollars(o.invested_total)} · </span>{percent(o.invested_share)}</span>
          {other > 0 && <span><i className="other-dot" />Other <span className="legend-amount">{dollars(o.other_total ?? 0)} · </span>{percent(other)}</span>}
          <span className="owed-legend"><i />Owed {dollars(o.owed)}<span className="legend-amount"> · inner ring</span></span>
        </div>
      </div>
    </section>
    <section className="account-ledger" aria-label="Accounts ranked by balance">
      {o.groups.map(group => <div className={`account-group ${group.key}`} key={group.key}>
        <header className="account-group-heading">
          <h2>{group.label}</h2>
          <span className="account-group-total">{dollars(group.total)} <small>{group.share_note}</small></span>
        </header>
        <ol start={group.accounts[0].rank}>
          {group.accounts.map(account => <li className="account-row" key={account.id} style={{ '--account-bar': account.bar } as CSSProperties}>
            <span className="account-rank" aria-hidden="true">{account.rank}</span>
            <span className="account-name" title={`${account.name} · ${account.kind_label}`}><strong>{account.name}</strong> <span className="account-desktop-meta">{account.source === 'manual' ? '' : account.institution}{mask(account.mask)}</span></span>
            <span className="account-row-detail">
              <span className="account-bar" aria-hidden="true"><i /></span>
              <span className="account-phone-meta">{account.source === 'manual' ? '' : account.institution}{mask(account.mask)}{account.note && `${account.source === 'manual' ? '' : ' · '}${account.note}`}</span>
            </span>
            <span className="account-note">{account.note}</span>
            <strong className="account-balance">{dollars(account.balance)}</strong>
            {(account.source === 'manual' || account.source === 'holding') && <div className="account-extra">
              <span className="account-details">{details(account)}</span>
              {actions?.(account)}
            </div>}
          </li>)}
        </ol>
      </div>)}
      {o.empty.length > 0 && <footer className="account-empty">+ {o.empty.length} empty {o.empty.length === 1 ? 'account' : 'accounts'}<span> · {o.empty.map(a => `${a.name}${mask(a.mask)}`).join(', ')}</span></footer>}
    </section>
  </>
}
