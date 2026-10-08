import { useEffect, useRef, useState } from 'react'
import { useData } from '../lib/api'

export default function VoiceInput({ transcript }: { transcript: (text: string) => void }) {
  const status = useData<{ engine: string | null; available: boolean; loading: boolean }>('stt/status')
  const [recording, setRecording] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const recorder = useRef<MediaRecorder | null>(null)
  const stream = useRef<MediaStream | null>(null)
  const wanted = useRef(false)
  const alive = useRef(true)
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  useEffect(() => {
    alive.current = true
    return () => { alive.current = false; wanted.current = false; clearTimeout(timer.current); if (recorder.current?.state === 'recording') recorder.current.stop(); stream.current?.getTracks().forEach(t => t.stop()) }
  }, [])
  function stop() {
    wanted.current = false
    clearTimeout(timer.current)
    if (recorder.current?.state === 'recording') recorder.current.stop()
    stream.current?.getTracks().forEach(t => t.stop())
    setRecording(false)
  }
  async function start() {
    if (wanted.current || busy) return
    wanted.current = true; setError('')
    try {
      const media = await navigator.mediaDevices.getUserMedia({ audio: true })
      stream.current = media
      if (!wanted.current || !alive.current) { media.getTracks().forEach(t => t.stop()); return }
      const value = new MediaRecorder(media)
      recorder.current = value
      const chunks: Blob[] = []
      value.ondataavailable = event => { if (event.data.size) chunks.push(event.data) }
      value.onstop = async () => {
        recorder.current = null
        if (!alive.current) return
        setBusy(true)
        try {
          const data = new FormData()
          data.append('audio', new Blob(chunks, { type: value.mimeType }), 'recording.webm')
          const response = await fetch('/api/stt', { method: 'POST', body: data })
          const result = await response.json()
          if (!response.ok) throw new Error(result.error || 'Transcription failed')
          if (alive.current) transcript(result.text)
        } catch (e) { if (alive.current) setError((e as Error).message) }
        finally { if (alive.current) setBusy(false) }
      }
      value.start(); setRecording(true)
      timer.current = setTimeout(stop, 60_000)
    } catch { wanted.current = false; stream.current?.getTracks().forEach(t => t.stop()); setError('Microphone unavailable or permission denied.') }
  }
  if (!status.data?.available || typeof MediaRecorder === 'undefined') return null
  return <div className="voice-input"><button type="button" aria-label="Microphone" aria-pressed={recording} disabled={busy}
    onPointerDown={e => { e.preventDefault(); e.currentTarget.setPointerCapture(e.pointerId); if (e.pointerType === 'touch' && recording) stop(); else void start() }}
    onPointerUp={e => { if (e.pointerType !== 'touch') stop() }} onPointerCancel={stop}
    onKeyDown={e => { if ((e.key === ' ' || e.key === 'Enter') && !e.repeat) { e.preventDefault(); void start() } }}
    onKeyUp={e => { if (e.key === ' ' || e.key === 'Enter') { e.preventDefault(); stop() } }}>
    {recording ? 'Recording… release to stop' : 'Hold to talk'}</button>
    <small>Touch: tap to start/stop. Transcript is not sent automatically.</small>
    {busy && <p role="status">{status.data.engine === 'faster-whisper' ? 'Preparing small.en (first use downloads the model), then transcribing…' : 'Transcribing…'}</p>}
    {error && <p role="alert">{error}</p>}
  </div>
}
