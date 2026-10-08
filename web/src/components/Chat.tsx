import { useRef, useState } from 'react'
import { HttpAgent } from '@ag-ui/client'
import { useUiBus } from '../lib/uiBus'
import { api, useAction, useData } from '../lib/api'
import { executeTool, tools, type Proposal } from '../lib/agentTools'
import type { Chart } from '../lib/types'
import SavedChart from './SavedChart'
import { chartInput } from '../lib/chart'
import VoiceInput from './VoiceInput'

export type ProviderStatus = { provider: string; model: string; key_present: boolean; overridden: boolean }
export function ProviderChip() {
  const status = useData<ProviderStatus>('llm/status')
  return <span className="badge provider-chip" title={status.data?.model}>Provider: {status.data?.provider || 'unavailable'}{status.data?.provider === 'fake' ? ' · test mode' : ''}</span>
}

type Entry = { id: string; kind: 'user' | 'assistant' | 'activity'; text: string } | { id: string; kind: 'chart'; chart: Chart } | { id: string; kind: 'proposal'; proposal: Proposal }

function PreviewCard({ chart }: { chart: Chart }) {
  const action = useAction(), [saved, setSaved] = useState(false)
  return <section className="inline-chart" aria-label="Chat chart"><h3>{chart.title}</h3><SavedChart chart={chart} />
    <button disabled={action.busy || saved} onClick={() => void action.run(async () => { await api('charts/save', chartInput(chart)); setSaved(true) })}>{saved ? 'Saved to Home' : 'Save'}</button>
    {action.error && <p role="alert">{action.error}</p>}</section>
}
export function ConfirmCard({ proposal }: { proposal: Proposal }) {
  const action = useAction(), [localResult, setResolved] = useState('')
  const stored = useData<Proposal>(`proposals/${encodeURIComponent(proposal.proposal_id)}`)
  const current = stored.data || proposal
  const resolved = localResult || (current.applied_at ? 'Applied' : current.cancelled_at ? 'Cancelled' : '')
  async function resolve(choice: 'apply' | 'cancel') {
    await api(`proposals/${encodeURIComponent(proposal.proposal_id)}/${choice}`, {})
    setResolved(choice === 'apply' ? 'Applied' : 'Cancelled')
  }
  return <section className="confirm-card" aria-label="Confirm change"><h3>Review change</h3><p>{stored.data ? current.summary : 'Loading stored proposal…'}</p>
    {stored.data && <pre>{JSON.stringify(current.diff, null, 2)}</pre>}
    {resolved ? <p role="status">{resolved}</p> : <div className="actions"><button disabled={action.busy || !stored.data} onClick={() => void action.run(() => resolve('apply'))}>Confirm</button><button disabled={action.busy || !stored.data} onClick={() => void action.run(() => resolve('cancel'))}>Cancel</button></div>}
    {(action.error || stored.error) && <p role="alert">{action.error || stored.error}</p>}</section>
}

export default function Chat() {
  const agent = useRef(new HttpAgent({ url: '/api/agent' }))
  const bus = useUiBus()
  const [open, setOpen] = useState(false), [text, setText] = useState('')
  const [entries, setEntries] = useState<Entry[]>([])
  const [busy, setBusy] = useState(false), [error, setError] = useState('')
  const add = (entry: Entry) => setEntries(v => [...v, entry])
  async function send() {
    if (!text.trim() || busy) return
    setBusy(true); setError('')
    agent.current.addMessage({ id: crypto.randomUUID(), role: 'user', content: text })
    add({ id: crypto.randomUUID(), kind: 'user', text }); setText('')
    agent.current.setState({ dashboard: bus.dashboard, page: location.hash, filters: bus.filters })
    const current = agent.current
    let expired = false
    let timer: ReturnType<typeof setTimeout> | undefined
    const timeout = new Promise<never>((_, reject) => {
      timer = setTimeout(() => {
        expired = true
        current.abortRun()
        // Discard a possibly incomplete tool-call conversation before retrying.
        agent.current = new HttpAgent({ url: '/api/agent' })
        reject(new Error('The request took too long. Please retry your message.'))
      }, 90_000)
    })
    const run = async () => {
      for (let turn = 0; turn <= 8 && !expired; turn++) {
        const pending: { id: string; name: string; args: Record<string, unknown> }[] = []
        const completed = new Set<string>()
        let runError = ''
        await current.runAgent({ tools }, {
          onTextMessageContentEvent: ({ event }) => {
            if (expired) return
            setEntries(v => {
              const old = v.find(e => e.id === event.messageId)
              return old ? v.map(e => e.id === event.messageId && e.kind === 'assistant' ? { ...e, text: e.text + event.delta } : e) : [...v, { id: event.messageId, kind: 'assistant', text: event.delta }]
            })
          },
          onToolCallEndEvent: ({ event, toolCallName, toolCallArgs }) => {
            pending.push({ id: event.toolCallId, name: toolCallName, args: toolCallArgs })
          },
          onToolCallResultEvent: ({ event }) => { completed.add(event.toolCallId) },
          onRunErrorEvent: ({ event }) => { runError = event.message },
        })
        if (expired) return
        if (runError) throw new Error(runError)
        const frontend = pending.filter(c => !completed.has(c.id))
        if (!frontend.length) break
        let displayOnly = true
        for (const call of frontend) {
          if (expired) return
          let result: unknown
          if (!['show_answer', 'show_chart', 'propose_change', 'ui_highlight'].includes(call.name)) displayOnly = false
          try {
            result = await executeTool(call.name, call.args,
              chart => { if (!expired) add({ id: call.id, kind: 'chart', chart }) },
              proposal => { if (!expired) add({ id: call.id, kind: 'proposal', proposal }) })
            if (expired) return
            const labels: Record<string, string> = { dashboard_move: 'Moved card', dashboard_resize: 'Resized card', dashboard_add: 'Added card', dashboard_remove: 'Removed card', ui_navigate: 'Opened page', ui_filter: 'Filtered page', ui_highlight: 'Highlighted item', show_chart: 'Displayed chart', show_answer: 'Displayed answer', reset_home: 'Restored default Home', propose_change: 'Requested confirmation' }
            add({ id: `${call.id}-activity`, kind: 'activity', text: labels[call.name] || call.name })
          } catch (e) {
            if (expired) return
            displayOnly = false
            result = { error: (e as Error).message }
            add({ id: `${call.id}-activity`, kind: 'activity', text: `Tool failed: ${(e as Error).message}` })
          }
          current.addMessage({ id: crypto.randomUUID(), role: 'tool', toolCallId: call.id, content: JSON.stringify(result) })
        }
        // All requested tools have run. Successful display-only batches are terminal;
        // mixed batches and failures still return results for model continuation.
        if (displayOnly) break
      }
    }
    try { await Promise.race([run(), timeout]) }
    catch (e) { setError((e as Error).message) }
    finally {
      clearTimeout(timer); setBusy(false)
      setEntries(v => v.filter(e => e.kind !== 'assistant' || e.text !== 'Working…'))
    }
  }
  return <div className="chat-widget">
    <button className="chat-toggle" aria-expanded={open} aria-controls="chat-drawer" onClick={() => setOpen(!open)}>Chat</button>
    {open && <aside id="chat-drawer" aria-label="Chat drawer" onKeyDown={e => { if (e.key === 'Escape') setOpen(false) }}>
      <header><h2>Ask ledgerlight</h2><ProviderChip /><button className="quiet" onClick={() => setOpen(false)} aria-label="Close chat">Close</button></header>
      <p className="sub">Layout changes happen live. Money changes always need your confirmation.</p>
      <div className="chat-history" aria-live="polite" aria-busy={busy}>{entries.map(entry => entry.kind === 'chart' ? <PreviewCard key={entry.id} chart={entry.chart} /> : entry.kind === 'proposal' ? <ConfirmCard key={entry.id} proposal={entry.proposal} /> : <p key={entry.id} className={`chat-${entry.kind}`}>{entry.text}</p>)}</div>
      {error && <p role="alert">{error}</p>}
      <form onSubmit={e => { e.preventDefault(); void send() }}><label>Message<textarea aria-label="Message" value={text} onChange={e => setText(e.target.value)} onKeyDown={e => {
        if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); void send() }
      }} required /></label><button disabled={busy || !text.trim()}>{busy ? 'Working…' : 'Send'}</button></form>
      <VoiceInput transcript={setText} />
    </aside>}
  </div>
}
