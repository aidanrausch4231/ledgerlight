import { useData } from '../lib/api'
import type { Proposal } from '../lib/agentTools'
import { ConfirmCard } from '../components/Chat'
import Feedback from '../components/Feedback'

export default function Proposals({ id }: { id?: string }) {
  const stored = useData<Proposal | Proposal[]>(id ? `proposals/${encodeURIComponent(id)}` : 'proposals')
  const pending = Array.isArray(stored.data) ? stored.data : []
  const proposal = stored.data && !Array.isArray(stored.data) ? stored.data : null
  return <>
    <h1>{id ? 'Review proposal' : 'Pending proposals'}</h1>
    <p>Financial changes are not applied until you press Confirm. Review the stored change below.</p>
    <Feedback error={stored.error} loading={!stored.data && !stored.error} />
    {id ? <>
      <a href="#/proposals">All pending proposals</a>
      {proposal && <ConfirmCard key={proposal.proposal_id} proposal={proposal} />}
    </> : <>
      {stored.data && !pending.length && <p>No pending proposals.</p>}
      <ul>{pending.map(item => <li key={item.proposal_id}><a href={`#/proposals/${encodeURIComponent(item.proposal_id)}`}>{item.summary}</a></li>)}</ul>
    </>}
  </>
}
