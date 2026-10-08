import { useCallback, useEffect, useState } from 'react'
import { usePlaidLink, type PlaidLinkOnSuccessMetadata } from 'react-plaid-link'
import type { AccountsOverview, Item, OverviewAccount, SyncStatus } from '../lib/types'
import { useData, api } from '../lib/api'
import Feedback from '../components/Feedback'
import AccountLedger from '../components/AccountLedger'
import ManualForm from '../components/ManualForm'
import './Accounts.css'

function historyLabel(item: Item) {
  const requested = item.history_days === 365 ? '12 months' : `${item.history_days} days`
  if (item.history_status !== 'HISTORICAL_UPDATE_COMPLETE') return `Importing your last ${requested}…`
  if (item.history_short) {
    const from = item.history_from ? `History from ${new Date(`${item.history_from}T12:00:00`).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}` : 'No dated history available'
    return `${from} — ${item.institution} sent less than the ${requested} requested`
  }
  return item.history_days === 365 ? 'Full year imported' : `Full ${item.history_days} days imported`
}

// Only what the server's duplicate-link check needs from Plaid Link metadata.
type LinkMetadata = {
  institution: { institution_id: string; name: string } | null
  accounts: { name: string; mask: string | null; type: string; subtype: string }[]
}

function linkMetadata(metadata: PlaidLinkOnSuccessMetadata): LinkMetadata {
  return {
    institution: metadata.institution ? { institution_id: metadata.institution.institution_id, name: metadata.institution.name } : null,
    accounts: (metadata.accounts || []).map(({ name, mask, type, subtype }) => ({ name, mask, type, subtype })),
  }
}

function PlaidLaunch({ token, onSuccess, onError }: { token: string; onSuccess: (token: string, metadata: LinkMetadata) => void; onError: (message: string) => void }) {
  const { open, ready, error } = usePlaidLink({ token, onSuccess: (publicToken, metadata) => {
    if (publicToken) onSuccess(publicToken, linkMetadata(metadata))
    else onError('Plaid did not return a public token. Please try again.')
  },
    onExit: error => { if (error) onError(error.display_message || 'Plaid Link closed with an error') },
  })
  useEffect(() => { if (error) onError('Unable to load Plaid Link') }, [error, onError])
  return <button disabled={!ready} onClick={() => open()}>Continue to Plaid</button>
}

export default function Accounts({ fake }: { fake: boolean }) {
  const [revision, setRevision] = useState(0)
  const accounts = useData<AccountsOverview>(`accounts/overview?revision=${revision}`)
  const [history, setHistory] = useState<SyncStatus | null>(null)
  const [statusError, setStatusError] = useState('')
  useEffect(() => {
    let active = true
    let lastSync: string | undefined
    const poll = async () => {
      try {
        const value = await api<SyncStatus>('sync/status')
        if (active) {
          const signature = JSON.stringify(value.items.map(item => [item.id, item.last_synced_at, item.history_status]))
          if (lastSync !== undefined && lastSync !== signature) window.dispatchEvent(new Event('ledgerlight-change'))
          lastSync = signature
          setHistory(value); setStatusError('')
        }
      } catch (e) { if (active) setStatusError((e as Error).message) }
    }
    void poll()
    const timer = window.setInterval(() => void poll(), 2000)
    return () => { active = false; window.clearInterval(timer) }
  }, [revision])
  const [token, setToken] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const reportError = useCallback((message: string) => setError(message), [])
  const [adding, setAdding] = useState(false)
  const [editing, setEditing] = useState<string | null>(null)
  const [removing, setRemoving] = useState<string | null>(null)
  const hasHoldings = accounts.data?.groups.some(g => g.accounts.some(a => a.source === 'holding'))
  function done(message: string) {
    setAdding(false); setEditing(null); setError(''); setMessage(message); setRevision(n => n + 1)
  }
  function rowActions(account: OverviewAccount) {
    const path = `${account.source === 'holding' ? 'holdings' : 'manual'}/${encodeURIComponent(account.id)}`
    if (editing === account.id) return <ManualForm account={account} onDone={done} onCancel={() => setEditing(null)} />
    if (removing === account.id) return <span className="account-actions" role="group" aria-label={`Confirm removing ${account.name}`}>
      <span>Remove {account.name} and its history?</span>
      <button className="danger" disabled={busy} onClick={() => void action(async () => {
        await api(path, undefined, 'DELETE'); setRemoving(null); setMessage(`Removed ${account.name}.`)
      })}>Confirm remove</button>
      <button className="quiet" onClick={() => setRemoving(null)}>Keep</button>
    </span>
    return <span className="account-actions">
      <button className="quiet" aria-label={`Edit ${account.name}`} onClick={() => { setRemoving(null); setEditing(account.id) }}>Edit</button>
      <button className="quiet" aria-label={`Remove ${account.name}`} onClick={() => { setEditing(null); setRemoving(account.id) }}>Remove</button>
    </span>
  }
  async function action(work: () => Promise<void>) {
    setBusy(true); setError(''); setMessage('')
    try { await work() } catch (e) { setError((e as Error).message) }
    finally { setBusy(false); setRevision(n => n + 1) }
  }
  function exchange(publicToken: string, metadata: LinkMetadata) {
    void action(async () => {
      // A duplicate link fails with HTTP 409; its message is shown in the alert.
      await api('plaid/exchange', { public_token: publicToken, link_token: token, metadata })
      setToken(null); setMessage('Account linked.')
    })
  }
  async function startLink() {
    const created = await api<{ link_token: string }>('plaid/link-token', {})
    if (fake) {
      await api('plaid/exchange', { public_token: `public-synthetic-ledgerlight:${created.link_token}`, link_token: created.link_token })
      setMessage('Account linked.')
    } else setToken(created.link_token)
  }
  return <div className="accounts-page">
    <header className="accounts-heading"><h1>Accounts</h1><div className="actions">
      <button className="account-link-desktop" disabled={busy} onClick={() => void action(startLink)}>Link account</button>
      <button className="quiet account-add-manual" aria-expanded={adding} onClick={() => setAdding(!adding)}>Add manually</button>
      {token && <PlaidLaunch token={token} onSuccess={exchange} onError={reportError} />}
      <button className="quiet" disabled={busy} onClick={() => void action(async () => {
        await api('sync', {}); setMessage('Sync complete.')
      })}>Sync now</button>
      {hasHoldings && <button className="quiet" disabled={busy} onClick={() => void action(async () => {
        const result = await api<{ refreshed: number; errors: unknown[] }>('holdings/refresh', {})
        setMessage(result.errors.length ? `Prices refreshed for ${result.refreshed}; ${result.errors.length} kept their last price.` : 'Prices refreshed.')
      })}>Refresh prices</button>}
    </div></header>
    {adding && <section className="manual-panel"><h2>Add manually</h2><ManualForm onDone={done} onCancel={() => setAdding(false)} /></section>}
    {message && <p role="status">{message}</p>}
    <Feedback error={error || accounts.error || statusError} loading={busy || !accounts.data || !history} />
    {accounts.data && (accounts.data.groups.length || accounts.data.empty.length
      ? <AccountLedger overview={accounts.data} actions={rowActions} />
      : <p>No accounts yet. Link an account to begin.</p>)}
    <button className="account-link-phone" disabled={busy} onClick={() => void action(startLink)}>Link account</button>
    <div className="linked-institutions">
    <h2>Linked institutions</h2>
    {history?.items.length === 0 && <p>No linked institutions.</p>}
    {history?.items.map(item => <section key={item.id}><h3>{item.institution}</h3>
      <p>Last sync: {item.last_synced_at || 'Never'}</p>
      {item.history_days < history.history_days ? <>
        <p>Linked with {item.history_days} days of history — relink to fetch a full year</p>
        <button disabled={busy} onClick={() => {
          if (window.confirm('Disconnect this institution and link it again? Local transactions, notes and tags will be kept. If Link is cancelled, use Link account to retry.')) void action(async () => {
            await api(`plaid/items/${encodeURIComponent(item.id)}/remove`, {})
            setToken(null)
            await startLink()
          })
        }}>Relink</button>
      </> : null}
      <p role="status">{historyLabel(item)}</p>
      <p>{item.transaction_count} transactions · Oldest date: {item.oldest_txn_date || 'Waiting for transactions'}</p>
      {item.history_status !== 'HISTORICAL_UPDATE_COMPLETE' && !item.background_active && <p>Automatic import paused. Select Sync now to check again.</p>}
      {item.last_error && <p role="alert">{item.last_error}</p>}
    </section>)}
    </div>
  </div>
}

