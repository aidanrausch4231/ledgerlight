export default function Feedback({ error, loading }: { error: string; loading: boolean }) {
  return error ? <p role="alert">{error}</p> : loading ? <p role="status">Loading…</p> : null
}
