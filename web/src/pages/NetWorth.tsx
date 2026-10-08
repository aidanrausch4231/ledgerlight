import DashboardCard from '../components/DashboardCard'

export default function NetWorth() {
  return <><h1>Net worth</h1><p className="almanac">A longer view of your recorded balances.</p>
    <section aria-label="Net worth history"><DashboardCard card={{ id: 'networth-page', kind: 'net_worth', props: {}, x: 0, y: 0, w: 12, h: 5 }} /></section>
  </>
}
