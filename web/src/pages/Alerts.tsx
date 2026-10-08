import { api, useAction, useData } from '../lib/api'
import Feedback from '../components/Feedback'

type Alert = { id: number; title: string; detail: string }
export default function Alerts() {
  const rows = useData<Alert[]>('alerts')
  const action = useAction()
  return <section aria-label="Alerts"><h2>Alerts</h2>
    <button disabled={action.busy} onClick={() => void action.run(() => api('alerts/refresh', {}))}>Refresh alerts</button>
    <Feedback error={action.error || rows.error} loading={!rows.data} />
    {rows.data?.map(a => <div role="status" key={a.id}><strong>{a.title}</strong> · {a.detail} <button disabled={action.busy} onClick={() => void action.run(() => api(`alerts/${a.id}/dismiss`, {}))}>Dismiss {a.title}</button></div>)}
  </section>
}
