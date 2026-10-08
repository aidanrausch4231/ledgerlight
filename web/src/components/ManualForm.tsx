import { useEffect, useState } from 'react'
import type { CoinSearch, ManualKind, OverviewAccount } from '../lib/types'
import { api, fields } from '../lib/api'
import Feedback from './Feedback'

type Kind = ManualKind | 'crypto' | 'stock'
const KINDS: [Kind, string][] = [
  ['student_loan', 'Student loan'], ['auto_loan', 'Auto loan'], ['personal_loan', 'Personal loan'],
  ['cash', 'Cash'], ['other_asset', 'Other asset'], ['crypto', 'Crypto'], ['stock', 'Stock'],
]
const isLoan = (kind: Kind) => kind.endsWith('_loan')
const optional = (value: string | undefined) => value === undefined || value === '' ? undefined : value

function CoinLookup({ symbol, coinId }: { symbol: string; coinId: string }) {
  const [result, setResult] = useState<{ symbol: string; value: CoinSearch | null; error: string } | null>(null)
  useEffect(() => {
    if (!symbol || coinId) return
    let active = true
    const timer = window.setTimeout(() => {
      // Only the symbol is sent; quantities and names stay local.
      api<CoinSearch>(`holdings/search?symbol=${encodeURIComponent(symbol)}`)
        .then(value => { if (active) setResult({ symbol, value, error: '' }) })
        .catch((e: Error) => { if (active) setResult({ symbol, value: null, error: e.message }) })
    }, 300)
    return () => { active = false; window.clearTimeout(timer) }
  }, [symbol, coinId])
  if (coinId) return <p className="coin-lookup" role="status">Using CoinGecko id {coinId}</p>
  if (!symbol || result?.symbol !== symbol) return null
  if (result.error) return <p className="coin-lookup" role="alert">{result.error}</p>
  const chosen = result.value?.chosen
  return <p className="coin-lookup" role="status">{chosen ? `Coin: ${chosen.name} (${chosen.id})` : `No coin matches ${symbol}; enter a CoinGecko id`}
    {chosen && result.value!.candidates.length > 1 && ` · ${result.value!.candidates.length - 1} other match${result.value!.candidates.length > 2 ? 'es' : ''}; set an id to pick another`}</p>
}

/** Add a manual account or holding, or edit one (kind fixed when editing). */
export default function ManualForm({ account, onDone, onCancel }: { account?: OverviewAccount; onDone: (message: string) => void; onCancel: () => void }) {
  const editing = account !== undefined
  const initial: Kind = account?.source === 'holding' ? account.holding_kind! : account?.manual_kind || 'student_loan'
  const [kind, setKind] = useState<Kind>(initial)
  const [symbol, setSymbol] = useState('')
  const [coinId, setCoinId] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const holding = kind === 'crypto' || kind === 'stock'
  const loan = isLoan(kind)
  const owed = account ? Math.abs(account.balance) : undefined

  async function submit(form: HTMLFormElement) {
    const f = fields(form)
    const auto = new FormData(form).has('auto_paydown')
    if (holding) {
      if (editing) {
        await api(`holdings/${encodeURIComponent(account.id)}`, { quantity: f.quantity, name: optional(f.name) }, 'PATCH')
        return `Updated ${f.name || account.name}.`
      }
      const added = await api<{ name: string }>('holdings', { kind, symbol: f.symbol, quantity: f.quantity, coin_id: optional(f.coin_id), name: optional(f.name) })
      return `Added ${added.name}.`
    }
    // An unchanged since date is omitted so a changed match restarts from today.
    const since = optional(f.payment_match_since)
    const match = loan ? {
      payment_match: editing ? f.payment_match.trim() : optional(f.payment_match.trim()),
      ...(since && since !== (account?.payment_match_since ?? undefined) ? { payment_match_since: since } : {}),
    } : {}
    const terms = loan ? { apr: editing ? f.apr : optional(f.apr), monthly_payment: editing ? f.payment : optional(f.payment), payment_day: editing ? f.payment_day : optional(f.payment_day), auto_paydown: auto, ...match } : {}
    if (editing) {
      const balanceChanged = Number(f.balance) !== owed
      await api(`manual/${encodeURIComponent(account.id)}`, { name: f.name, ...(balanceChanged ? { balance: f.balance } : {}), ...terms }, 'PATCH')
      return `Updated ${f.name}.`
    }
    await api('manual', { kind, name: f.name, balance: f.balance, ...terms })
    return `Added ${f.name}.`
  }

  return <form className="manual-form" aria-label={editing ? `Edit ${account.name}` : 'Add manually'} onSubmit={e => {
    e.preventDefault()
    const form = e.currentTarget
    setBusy(true); setError('')
    submit(form).then(onDone).catch((err: Error) => setError(err.message)).finally(() => setBusy(false))
  }}>
    {!editing && <label>Kind<select name="kind" value={kind} onChange={e => setKind(e.target.value as Kind)}>
      {KINDS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
    </select></label>}
    {holding ? <>
      {!editing && <label>{kind === 'crypto' ? 'Symbol' : 'Ticker'}<input name="symbol" required maxLength={20} autoCapitalize="characters" placeholder={kind === 'crypto' ? 'BTC' : 'AAPL'} onChange={e => setSymbol(e.target.value.trim().toUpperCase())} /></label>}
      <label>Quantity<input name="quantity" type="number" min="0" step="any" required defaultValue={account?.quantity} /></label>
      {kind === 'crypto' && !editing && <label>CoinGecko id (optional)<input name="coin_id" placeholder="bitcoin" onChange={e => setCoinId(e.target.value.trim())} /></label>}
      <label>{editing ? 'Name' : 'Name (optional)'}<input name="name" defaultValue={account?.name} /></label>
      {kind === 'crypto' && !editing && <CoinLookup symbol={symbol} coinId={coinId} />}
    </> : <>
      <label>Name<input name="name" required defaultValue={account?.name} /></label>
      <label>{loan ? 'Amount owed' : 'Balance'}<input name="balance" type="number" min="0" step="0.01" required defaultValue={owed} /></label>
      {loan && <>
        <label>APR (%)<input name="apr" type="number" min="0" max="100" step="0.001" defaultValue={account?.apr ?? undefined} /></label>
        <label>Monthly payment<input name="payment" type="number" min="0" step="0.01" defaultValue={account?.monthly_payment ?? undefined} /></label>
        <label>Payment day<input name="payment_day" type="number" min="1" max="28" step="1" placeholder="1" defaultValue={account?.payment_day ?? undefined} /></label>
        <label className="manual-check"><input name="auto_paydown" type="checkbox" defaultChecked={account?.auto_paydown} />Auto paydown each month</label>
        <label>Pays down from transactions matching<input name="payment_match" maxLength={100} placeholder="ACME" defaultValue={account?.payment_match ?? ''} /></label>
        <label>Matching since<input name="payment_match_since" type="date" defaultValue={account?.payment_match_since ?? ''} /></label>
        <p className="manual-hint">Posted outflows in linked accounts whose name or merchant contains this text reduce the amount owed after each sync. Use this or auto paydown, not both.</p>
      </>}
    </>}
    <div className="actions">
      <button disabled={busy}>{editing ? 'Save changes' : 'Add account'}</button>
      <button type="button" className="quiet" onClick={onCancel}>Cancel</button>
    </div>
    <Feedback error={error} loading={false} />
  </form>
}
