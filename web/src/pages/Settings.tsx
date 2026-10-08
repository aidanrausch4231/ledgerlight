import { useState } from 'react'
import { api, fields, useAction, useData } from '../lib/api'
import Feedback from '../components/Feedback'
import type { Account } from '../lib/types'
import type { ProviderStatus } from '../components/Chat'

export default function Settings() {
  const settings = useData<Record<string, number | string>>('settings')
  const accounts = useData<Account[]>('accounts')
  const action = useAction()
  const provider = useData<ProviderStatus>('llm/status')
  // Status refreshes must not replace a choice the user is about to save.
  const [selection, setSelection] = useState<string | null>(null)
  return <><h1>Settings</h1>
    <section aria-label="Agent provider"><h2>Agent provider</h2>
      <p>Cloud providers send your conversation and requested ledger results to that provider. Keys are read from server environment variables only.</p>
      {provider.data?.overridden && <p role="status">LEDGERLIGHT_LLM_PROVIDER overrides the saved selection. Active: {provider.data.provider}.</p>}
      <form onSubmit={e => { e.preventDefault(); const f = fields(e.currentTarget); void action.run(() => api('llm/provider', { provider: f.provider })) }}>
        <label>Provider<select aria-label="Provider" name="provider" disabled={!provider.data || action.busy} value={selection ?? (provider.data?.provider === 'fake' ? 'local' : provider.data?.provider || 'local')} onChange={e => setSelection(e.target.value)}><option value="local">Local · Ollama</option><option value="claude">Claude</option><option value="openai">OpenAI</option></select></label><button disabled={!provider.data || action.busy}>Save provider</button>
      </form><p>{provider.data?.model} · {provider.data?.key_present ? 'Key configured' : 'No cloud key configured'}</p>
    </section><Feedback error={action.error || provider.error || settings.error || accounts.error} loading={!settings.data || !accounts.data} />
    {settings.data && <form key={JSON.stringify(settings.data)} onSubmit={e => {
      e.preventDefault(); const f = fields(e.currentTarget)
      void action.run(async () => { for (const [key, value] of Object.entries(f)) if (value !== '') await api('settings', { key, value: Number(value) }); await api('alerts/refresh', {}) })
    }}>
      <label>Bill warning days<input name="bill_days" type="number" min="0" max="36500" required defaultValue={settings.data.bill_days} /></label>
      <label>Low balance threshold<input name="low_balance_threshold" type="number" min="0" step="0.01" required defaultValue={settings.data.low_balance_threshold} /></label>
      {accounts.data?.map(a => <label key={a.id}>Threshold for {a.name}<input name={`low_balance_threshold:${a.id}`} type="number" min="0" step="0.01" placeholder="Use global threshold" defaultValue={settings.data?.[`low_balance_threshold:${a.id}`] ?? ''} /></label>)}
      <button disabled={action.busy}>Save thresholds</button>
    </form>}
  </>
}
