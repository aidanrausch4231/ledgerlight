import { useSyncExternalStore } from 'react'
import { api } from './api'
import type { Chart } from './types'

export type Answer = { title: string; summary: string; charts: Chart[] }
export function showAnswer(answer: Answer | null) { notify({ answer, answerVersion: state.answerVersion + 1 }) }
export function clearReceipt() { notify({ receipt: null }); clearMark() }
let toolNavigation: string | null = null
export function navigationChanged() {
  if (toolNavigation !== window.location.hash) clearReceipt()
  toolNavigation = null
}

export type Card = { id: string; kind: string; props: { chart_id?: number }; x: number; y: number; w: number; h: number }
export type Dashboard = { cards: Card[]; version: number; seq: number }
export type UiEvent = { seq: number; type: string; actor: 'user' | 'agent' | 'cli' | 'mcp'; payload: Record<string, unknown> }
type Receipt = { text: string; undo: () => Promise<void> }
type State = { answerVersion: number; answer: Answer | null; dashboard: Dashboard | null; filters: Record<string, Record<string, string>>; marked: string | null; markedVersion: number | null; receipt: Receipt | null; error: string; connected: boolean }
let state: State = { answerVersion: 0, answer: null, dashboard: null, filters: {}, marked: null, markedVersion: null, receipt: null, error: '', connected: false }
const listeners = new Set<() => void>()
const notify = (patch: Partial<State>) => { state = { ...state, ...patch }; listeners.forEach(fn => fn()) }
const subscribe = (fn: () => void) => { listeners.add(fn); return () => { listeners.delete(fn) } }
export const useUiBus = () => useSyncExternalStore(subscribe, () => state)
export const titles: Record<string, string> = {
  spending_vs_last_month: 'Spending, this month vs last', cashflow: 'Cash flow', upcoming_bills: 'Upcoming bills',
  net_worth: 'Net worth', budgets: 'Budgets', goals: 'Savings goals', alerts: 'Alerts',
  recent_transactions: 'Recent transactions', top_merchants: 'Top merchants', chart: 'Saved chart',
}
let markTimer: ReturnType<typeof setTimeout> | undefined
let highlightTimer: ReturnType<typeof setTimeout> | undefined
let observer: MutationObserver | undefined
let highlighted: string | null = null
function clearHighlight() {
  clearTimeout(highlightTimer); observer?.disconnect(); observer = undefined; highlighted = null
  document.querySelectorAll('.ui-highlight').forEach(el => el.classList.remove('ui-highlight'))
}
function clearMark() { clearTimeout(markTimer); notify({ marked: null, markedVersion: null }) }
function receipt(text: string, undo: () => Promise<void>, actor: string) {
  if (actor !== 'user') notify({ receipt: { text: `${actor === 'cli' ? 'CLI' : actor === 'mcp' ? 'MCP' : 'Agent'} ${text}`, undo } })
}
export function navigate(page: string, actor = 'agent') {
  const previous = window.location.hash
  const next = page === 'home' ? '#/' : `#/${page}`
  toolNavigation = actor !== 'user' && next !== window.location.hash ? next : null
  if (actor === 'user') clearReceipt()
  window.location.hash = next
  receipt(`opened ${page}`, async () => { window.location.hash = previous; notify({ receipt: null }) }, actor)
}
export function filter(page: string, filters: Record<string, string>, actor = 'agent') {
  const previous = state.filters[page] || {}
  notify({ filters: { ...state.filters, [page]: filters } })
  if (actor !== 'user') highlight(`page:${page}`, 'user')
  else clearHighlight()
  receipt(`filtered ${page}`, async () => { filter(page, previous, 'user'); notify({ receipt: null }) }, actor)
}
export function highlight(target: string, actor = 'agent') {
  const previous = highlighted
  clearHighlight(); highlighted = target
  const apply = () => document.querySelectorAll('[data-ui-id]').forEach(el => {
    if (el.getAttribute('data-ui-id') === target) el.classList.add('ui-highlight')
  })
  apply(); observer = new MutationObserver(apply); observer.observe(document.body, { childList: true, subtree: true })
  highlightTimer = setTimeout(clearHighlight, 2000)
  receipt(`highlighted ${target}`, async () => { clearHighlight(); if (previous) highlight(previous, 'user'); notify({ receipt: null }) }, actor)
}
export function clear(actor = 'agent') {
  const previous = { filters: state.filters, marked: state.marked, markedVersion: state.markedVersion, highlighted }
  clearHighlight(); clearMark(); notify({ filters: {}, receipt: null })
  receipt('cleared UI filters and marks', async () => {
    notify({ filters: previous.filters, marked: previous.marked, markedVersion: previous.markedVersion, receipt: null })
    if (previous.marked) markTimer = setTimeout(() => notify({ marked: null }), 8000)
    if (previous.highlighted) highlight(previous.highlighted, 'user')
  }, actor)
}
export function setPageFilters(page: string, filters: Record<string, string>) {
  notify({ filters: { ...state.filters, [page]: filters } })
}
const seen = new Set<number>()
export function applyEvent(event: UiEvent) {
  if (seen.has(event.seq)) return
  seen.add(event.seq)
  if (seen.size > 2000) seen.delete(seen.values().next().value!)
  const p = event.payload
  const action = event.type.split('.')[1]
  if (event.type.startsWith('dashboard.')) {
    const dashboard = { cards: p.cards as Card[], version: p.version as number, seq: event.seq }
    if (state.dashboard && dashboard.version < state.dashboard.version) return
    notify({ dashboard, error: '' })
    if (action === 'list') return // A CLI list journals a snapshot, not a visual change.
    clearMark()
    if (event.actor !== 'user' || action === 'reset_default') {
      const id = p.id as string | null
      notify({ marked: id, markedVersion: dashboard.version })
      markTimer = setTimeout(() => notify({ marked: null }), 8000)
      const verbs: Record<string, string> = { add: 'added', move: 'moved', resize: 'resized', remove: 'removed', layout: 'arranged', undo: 'undid changes to', reset_default: 'restored default for' }
      receipt(`${verbs[action] || action} ${titles[p.kind as string] || 'dashboard'}`, async () => {
        await dashboardCommand('undo', { expected_version: dashboard.version }, 'user')
      }, event.actor)
      if (event.actor === 'user') notify({ receipt: { text: 'Restored default Home layout', undo: async () => {
        await dashboardCommand('undo', { expected_version: dashboard.version }, 'user')
      } } })
    } else notify({ receipt: null })
  } else if (event.type === 'ui.navigate') navigate(p.page as string, event.actor)
  else if (event.type === 'ui.filter') filter(p.page as string, p.filters as Record<string, string>, event.actor)
  else if (event.type === 'ui.highlight') highlight(p.target as string, event.actor)
  else if (event.type === 'ui.clear') clear(event.actor)
}
export async function dashboardCommand(action: string, payload: object = {}, actor = 'agent') {
  try {
    const result = await api<Dashboard & { event: UiEvent }>(`dashboard/${action}`, { ...payload, actor })
    applyEvent(result.event)
    return result
  } catch (e) {
    // A failed/stale drag must not leave an unsaved RGL position on screen.
    try { notify({ dashboard: await api<Dashboard>('dashboard') }) } catch { /* Keep the original action error. */ }
    notify({ error: (e as Error).message }); throw e
  }
}
export const add = (kind: string, props = {}, actor = 'agent') => dashboardCommand('add', { kind, props }, actor)
export const move = (id: string, x: number, y: number, actor = 'agent') => dashboardCommand('move', { id, x, y }, actor)
export const resize = (id: string, w: number, h: number, actor = 'agent') => dashboardCommand('resize', { id, w, h }, actor)
export const remove = (id: string, actor = 'agent') => dashboardCommand('remove', { id }, actor)
export const resetHome = (actor = 'agent') => dashboardCommand('default/reset', {}, actor)
export const undo = () => dashboardCommand('undo', {}, 'user')
export async function undoReceipt() {
  try { await state.receipt?.undo() } catch (e) { notify({ error: (e as Error).message }) }
}

// App owns this lifetime, never a page/card: exactly one stream per tab.
export function startUiBus() {
  let active = true
  let source: EventSource | undefined
  let retry: ReturnType<typeof setTimeout> | undefined
  async function start() {
    try {
      const dashboard = await api<Dashboard>('dashboard')
      if (!active) return
      notify({ dashboard, error: '' })
      source = new EventSource(`/api/events?after=${dashboard.seq}`)
      source.onopen = () => notify({ connected: true, error: '' })
      source.onerror = () => notify({ connected: false }) // Native reconnect preserves Last-Event-ID.
      source.onmessage = message => {
        try { applyEvent(JSON.parse(message.data) as UiEvent) }
        catch { notify({ error: 'Unable to apply a UI event. Reload to resynchronize.' }) }
      }
    } catch (e) {
      if (!active) return
      notify({ error: (e as Error).message }); retry = setTimeout(() => void start(), 2000)
    }
  }
  void start()
  return () => { active = false; source?.close(); clearTimeout(retry); clearHighlight(); clearTimeout(markTimer) }
}
