import { useEffect, useState } from 'react'

export async function api<T>(path: string, body?: object, method?: 'POST' | 'PATCH' | 'DELETE'): Promise<T> {
  const write = body !== undefined || method !== undefined
  const response = await fetch(`/api/${path}`, !write ? undefined : {
    method: method || 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body ?? {}),
  })
  const value = await response.json()
  if (!response.ok) throw new Error(value.error || `HTTP ${response.status}`)
  if (write && !path.endsWith('/preview')) window.dispatchEvent(new Event('ledgerlight-change'))
  return value as T
}

export function useData<T>(path: string) {
  const [revision, setRevision] = useState(0)
  const [result, setResult] = useState<{ path: string; data: T | null; error: string }>({ path, data: null, error: '' })
  useEffect(() => {
    const refresh = () => setRevision(n => n + 1)
    window.addEventListener('ledgerlight-change', refresh)
    return () => window.removeEventListener('ledgerlight-change', refresh)
  }, [])
  useEffect(() => {
    let active = true
    api<T>(path).then(data => { if (active) setResult({ path, data, error: '' }) })
      .catch((e: Error) => { if (active) setResult({ path, data: null, error: e.message }) })
    return () => { active = false }
  }, [path, revision])
  return result.path === path ? result : { data: null, error: '' }
}

export function useAction() {
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  async function run(work: () => Promise<unknown>) {
    setBusy(true); setError('')
    try { await work() } catch (e) { setError((e as Error).message) }
    finally { setBusy(false) }
  }
  return { error, busy, run }
}

export const money = (amount: number) => amount.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
export const fields = (form: HTMLFormElement) => Object.fromEntries(new FormData(form)) as Record<string, string>
