import { useEffect, useState } from 'react'
import { useData } from './lib/api'
import { startUiBus, undoReceipt, useUiBus, navigationChanged, clearReceipt } from './lib/uiBus'
import Feedback from './components/Feedback'
import NavIcon from './components/NavIcon'
import NetWorth from './pages/NetWorth'
import Home from './pages/Home'
import Transactions from './pages/Transactions'
import Recurring from './pages/Recurring'
import Accounts from './pages/Accounts'
import Budgets from './pages/Budgets'
import Rules from './pages/Rules'
import Goals from './pages/Goals'
import Bills from './pages/Bills'
import Settings from './pages/Settings'
import Alerts from './pages/Alerts'
import Proposals from './pages/Proposals'
import AnswerPanel from './components/AnswerPanel'
import Chat, { ProviderChip } from './components/Chat'

export default function App() {
  const [page, setPage] = useState(window.location.hash.slice(1) || '/')
  const [menu, setMenu] = useState(false)
  const [alertsOpen, setAlertsOpen] = useState(false)
  const [theme, setTheme] = useState(() => localStorage.getItem('ledgerlight-theme') || 'system')
  const bus = useUiBus()
  const status = useData<{ fake_plaid: boolean; plaid_env: string; test_mode?: boolean }>('status')
  const alerts = useData<{ id: number; kind: string; title: string; detail: string; account_id: string | null }[]>('alerts')
  useEffect(startUiBus, [])
  useEffect(() => {
    const change = () => { navigationChanged(); setPage(window.location.hash.slice(1) || '/'); setMenu(false) }
    window.addEventListener('hashchange', change)
    return () => window.removeEventListener('hashchange', change)
  }, [])
  useEffect(() => {
    if (theme === 'system') delete document.documentElement.dataset.theme
    else document.documentElement.dataset.theme = theme
    localStorage.setItem('ledgerlight-theme', theme)
  }, [theme])
  const pages: Record<string, React.ReactNode> = {
    '/': <Home />, '/transactions': <Transactions />, '/recurring': <Recurring />,
    '/accounts': <Accounts fake={status.data?.fake_plaid === true} />, '/budgets': <Budgets />,
    '/networth': <NetWorth />, '/rules': <Rules />, '/goals': <Goals />, '/bills': <Bills />, '/settings': <Settings />,
    '/proposals': <Proposals />,
  }
  const low = alerts.data?.find(a => a.kind === 'low_balance')
  return <div className="app-shell" onClickCapture={event => {
    if ((event.target as HTMLElement).closest('a[href^="#/"]')) clearReceipt()
  }}>
    <a className="skip" href="#main" onClick={event => { event.preventDefault(); document.getElementById('main')?.focus() }}>Skip to content</a>
    <aside className={`rail ${menu ? 'open' : ''}`}>
      <a className="brand" href="#/" aria-label="ledgerlight home"><svg viewBox="0 0 26 18" aria-hidden="true"><path d="M1 5c3-2.5 5-2.5 8 0s5 2.5 8 0 5-2.5 8 0M1 10c3-2.5 5-2.5 8 0s5 2.5 8 0 5-2.5 8 0M1 15c3-2.5 5-2.5 8 0s5 2.5 8 0 5-2.5 8 0" /></svg><span>ledgerlight</span></a>
      <button className="menu-toggle quiet" aria-expanded={menu} aria-controls="main-nav" onClick={() => setMenu(!menu)}>Menu</button>
      <nav id="main-nav" aria-label="Main">{Object.keys(pages).map(path => {
        const label = path === '/' ? 'Home' : path === '/networth' ? 'Net worth' : path[1].toUpperCase() + path.slice(2)
        return <a key={path} href={`#${path}`} aria-label={label} title={label} data-ui-id={`nav:${path === '/' ? 'home' : path.slice(1)}`} aria-current={page === path ? 'page' : undefined}>
          <NavIcon path={path} /><span className="nav-label">{label}</span></a>
      })}</nav>
      <div className="rail-foot"><b>Local, by design</b><br />Your ledger stays with you.<br /><span role="status">{bus.connected ? 'Live UI connected' : 'Reconnecting live UI…'}</span></div>
    </aside>
    <main id="main" tabIndex={-1}>
      <header className="topbar"><p className="eyebrow">{new Date().toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long' })}</p>
        <div className="top-actions"><ProviderChip />{(status.data?.fake_plaid || status.data?.test_mode) && <span className="badge">test mode</span>}
          <button className="quiet bell" aria-label={`Alerts (${alerts.data?.length || 0})`} aria-expanded={alertsOpen} aria-controls="alert-panel" onClick={() => setAlertsOpen(!alertsOpen)}>
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 17h14l-2-3V9a5 5 0 0 0-10 0v5zM10 20h4" /></svg>{alerts.data?.length || 0}</button>
          <button className="quiet" aria-label="Toggle dark mode" onClick={() => setTheme((theme === 'dark' || (theme === 'system' && matchMedia('(prefers-color-scheme: dark)').matches)) ? 'light' : 'dark')}>◐</button>
          <button className="quiet system-theme" onClick={() => setTheme('system')} aria-pressed={theme === 'system'}>System theme</button>
        </div>
      </header>
      <Feedback error={status.error || bus.error} loading={false} />
      {bus.receipt && <div className="receipt" role="status"><span>{bus.receipt.text}</span><button className="chip" onClick={() => void undoReceipt()}>Undo</button></div>}
      {low && <div className="notice" role="status"><p><strong>{low.title}</strong> · {low.detail}</p><a href="#/accounts">View account</a></div>}
      <div id="alert-panel" hidden={!alertsOpen && page !== '/settings'}><Alerts /></div>
      <div className="page" data-ui-id={`page:${page === '/' ? 'home' : page.slice(1)}`}><AnswerPanel />{page.startsWith('/proposals/') ? <Proposals key={page} id={page.slice('/proposals/'.length)} /> : pages[page] || <Home />}</div>
    </main>
    <Chat />
  </div>
}
