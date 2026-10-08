import type { Tool } from '@ag-ui/core'
import * as bus from './uiBus'
import { api } from './api'
import type { Chart } from './types'

const string = { type: 'string' }, integer = { type: 'integer' }, object = { type: 'object' }
function tool(name: string, description: string, properties: object, required = Object.keys(properties)): Tool {
  return { name, description, parameters: { type: 'object', properties, required, additionalProperties: false } }
}
export const tools: Tool[] = [
  tool('ui_navigate', 'Open a page: home, transactions, budgets, bills, recurring, accounts, networth, rules, goals, settings', { page: string }),
  tool('ui_filter', 'Set page filters', { page: string, filters: { type: 'object', additionalProperties: string } }),
  tool('ui_highlight', 'Highlight stable target such as card:ID or page:budgets', { target: string }),
  tool('dashboard_add', 'Add a dashboard card by kind with props', { kind: string, props: object }),
  tool('dashboard_move', 'Move existing card to grid position', { id: string, x: integer, y: integer }),
  tool('dashboard_resize', 'Resize existing card', { id: string, w: integer, h: integer }),
  tool('dashboard_remove', 'Remove a dashboard card, not source data', { id: string }),
  tool('reset_home', 'Restore the saved default Home layout (undoable)', {}),
  tool('show_answer', 'Display one answer above the current page, using the exact charts specs from spending ask', { title: string, summary: string, charts: { type: 'array', items: object } }),
  tool('show_chart', 'Show the complete chart preview returned by CLI, with a user Save button', { chart: object }),
  tool('propose_change', 'Show a stored --propose result for user confirmation. Never applies it.', { proposal_id: string, summary: string, diff: object }),
]
export type Proposal = { proposal_id: string; summary: string; diff: object; applied_at?: string | null; cancelled_at?: string | null }
export async function executeTool(name: string, args: Record<string, unknown>, chart: (c: Chart) => void, proposal: (p: Proposal) => void) {
  switch (name) {
    case 'ui_navigate': {
      const page = String(args.page)
      if (!['home', 'transactions', 'budgets', 'bills', 'recurring', 'accounts', 'networth', 'rules', 'goals', 'settings'].includes(page)) throw new Error('Unknown page')
      bus.navigate(page, 'agent'); return { opened: page }
    }
    case 'ui_filter': {
      const event = await api<bus.UiEvent>('ui/filter', { ...args, actor: 'agent' })
      bus.applyEvent(event); return { filtered: args.page }
    }
    case 'ui_highlight': bus.highlight(String(args.target), 'agent'); return { highlighted: args.target }
    case 'dashboard_add': return bus.add(String(args.kind), args.props || {}, 'agent')
    case 'dashboard_move': return bus.move(String(args.id), Number(args.x), Number(args.y), 'agent')
    case 'dashboard_resize': return bus.resize(String(args.id), Number(args.w), Number(args.h), 'agent')
    case 'dashboard_remove': return bus.remove(String(args.id), 'agent')
    case 'reset_home': return bus.resetHome('agent')
    case 'show_answer': {
      if (typeof args.title !== 'string' || typeof args.summary !== 'string' || !Array.isArray(args.charts) || args.charts.length > 2) throw new Error('Invalid answer')
      const charts = args.charts.map(spec => {
        if (!spec || spec.mark !== 'bar' || typeof spec.usermeta?.title !== 'string' || typeof spec.usermeta?.sql !== 'string' || !Array.isArray(spec.data?.values)) throw new Error('Invalid answer chart')
        return { id: 0, title: spec.usermeta.title, sql: spec.usermeta.sql, spec, rows: spec.data.values } as Chart
      })
      bus.showAnswer({ title: args.title, summary: args.summary, charts })
      return { shown: args.title, saved: false }
    }
    case 'show_chart': {
      const c = args.chart as Chart
      if (!c || typeof c.title !== 'string' || typeof c.sql !== 'string' || !c.spec || !Array.isArray(c.rows)) throw new Error('Invalid chart preview')
      chart(c); return { shown: c.title, saved: false }
    }
    case 'propose_change': {
      // Fetch the stored summary: never trust a model's description of a write.
      const p = await api<Proposal>(`proposals/${encodeURIComponent(String(args.proposal_id))}`)
      proposal(p); return { displayed: p.proposal_id, awaiting_user_confirmation: true }
    }
    default: throw new Error('Unknown frontend tool')
  }
}
