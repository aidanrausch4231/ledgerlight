import type { TopLevelSpec } from 'vega-lite'
export type HtmlSpec = { kind: 'html'; html: string }
export type Chart = { id: number; title: string; sql?: string; version?: number; srcdoc?: string; spec: TopLevelSpec | HtmlSpec; rows: Record<string, unknown>[] }
export type Account = { id: string; name: string; balance: number; available: number | null; currency: string | null; type: string | null; mask: string | null }
export type Item = { id: string; institution: string; last_synced_at: string | null; last_error: string | null; history_status: string; history_days: number; oldest_txn_date: string | null; transaction_count: number; background_active: boolean; history_from: string | null; history_short: boolean }
export type ManualKind = 'student_loan' | 'auto_loan' | 'personal_loan' | 'cash' | 'other_asset'
export type OverviewAccount = { id: string; rank: number; name: string; institution: string; mask: string | null; type: string | null; subtype: string | null; kind: 'cash' | 'investment' | 'credit' | 'crypto' | 'other'; kind_label: string; balance: number; available: number | null; credit_limit: number | null; note: string; bar: number
  source?: 'plaid' | 'manual' | 'holding'
  // Holding rows
  holding_kind?: 'crypto' | 'stock'; symbol?: string; coin_id?: string | null; quantity?: number; price?: number | null; price_change_24h?: number | null; price_as_of?: string | null; price_error?: string | null
  // Manual rows
  manual_kind?: ManualKind; apr?: number | null; monthly_payment?: number | null; payment_day?: number | null; auto_paydown?: boolean
  payment_match?: string | null; payment_match_since?: string | null; payments_applied?: number; last_payment?: { date: string; amount: number } | null }
export type AccountsOverview = { net_worth: number; held: number; owed: number; cash_total: number; invested_total: number; cash_share: number; invested_share: number; owed_ratio: number; crypto_total?: number; other_total?: number; other_share?: number; groups: { key: 'investments' | 'crypto' | 'cash' | 'other' | 'owed'; label: string; total: number; share_note: string; accounts: OverviewAccount[] }[]; empty: { id: string; name: string; institution: string; mask: string | null }[] }
export type CoinSearch = { symbol: string; candidates: { id: string; symbol: string; name: string; market_cap_rank: number | null }[]; chosen: { id: string; name: string } | null }
export type SyncStatus = { history_days: number; items: Item[] }
export type Transaction = { id: string; date: string; name: string; merchant: string | null; amount: number; category: string; pending: boolean; note: string | null; hidden: boolean; tags: string[]; splits: { category: string; amount: number }[]; split_cleared_at: string | null }
export type Stream = { id: string; direction: 'in' | 'out'; description: string; average_amount: number; predicted_next_date: string | null; frequency: string; is_active: boolean; user_status: string | null }

