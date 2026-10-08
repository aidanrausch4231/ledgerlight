import { useEffect, useRef, useState } from 'react'
import embed from 'vega-embed'
import type { TopLevelSpec } from 'vega-lite'
import type { Chart } from '../lib/types'
import { isHtml, sandboxDocument } from '../lib/chart'
import Feedback from './Feedback'

function VegaChart({ chart }: { chart: Chart }) {
  const container = useRef<HTMLDivElement>(null)
  const [error, setError] = useState('')
  const [appearance, setAppearance] = useState({ ink: '', rule: '', water: '', accent: '', width: 300, height: 240 })
  useEffect(() => {
    const update = () => {
      const css = getComputedStyle(document.documentElement)
      const token = (name: string) => css.getPropertyValue(name).trim()
      const body = container.current?.closest('.card-body')
      const next = { ink: token('--ink-2'), rule: token('--rule-soft'), water: token('--water-deep'), accent: token('--overprint'), width: Math.max(100, container.current?.clientWidth || 300), height: body ? Math.max(100, body.clientHeight - 60) : 240 }
      setAppearance(old => JSON.stringify(old) === JSON.stringify(next) ? old : next)
    }
    update()
    const theme = new MutationObserver(update)
    theme.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
    const media = matchMedia('(prefers-color-scheme: dark)')
    media.addEventListener('change', update)
    const size = new ResizeObserver(update)
    if (container.current) size.observe(container.current)
    const body = container.current?.closest('.card-body')
    if (body) size.observe(body)
    return () => { theme.disconnect(); size.disconnect(); media.removeEventListener('change', update) }
  }, [])
  useEffect(() => {
    let disposed = false
    let finalize: (() => void) | undefined
    if (container.current) {
      // Preview tools are model-controlled. Only our simple local-data schema
      // reaches Vega; never forward URLs, expressions, transforms or hrefs.
      const source = chart.spec as { mark?: unknown; encoding?: Record<string, { field?: unknown; type?: unknown; title?: unknown }> }
      const mark = String(source.mark)
      const encoding = Object.fromEntries(Object.entries(source.encoding || {}).filter(([key]) => ['x', 'y', 'theta', 'color'].includes(key)).map(([key, value]) => [key, {
        field: String(value.field || ''), type: value.type === 'quantitative' ? 'quantitative' : 'nominal', title: String(value.title || ''),
      }]))
      const spec = {
        mark: ['bar', 'line', 'area', 'arc'].includes(mark) ? mark : 'bar', encoding,
        width: appearance.width, height: appearance.height,
        autosize: { type: 'fit', contains: 'padding' }, background: 'transparent', data: { values: chart.rows },
        config: {
          view: { stroke: null }, mark: { color: appearance.water },
          range: { category: [appearance.water, appearance.accent, appearance.ink] },
          axis: { labelColor: appearance.ink, titleColor: appearance.ink, gridColor: appearance.rule, domainColor: appearance.rule, tickColor: appearance.rule, labelFont: 'Schibsted Grotesk', titleFont: 'Schibsted Grotesk' },
          axisX: { labelAngle: -30, labelLimit: 90, titlePadding: 8 },
          legend: { labelColor: appearance.ink, titleColor: appearance.ink },
        },
      } as TopLevelSpec
      embed(container.current, spec, { actions: false, renderer: 'svg' }).then(result => {
        if (disposed) result.finalize()
        else finalize = () => result.finalize()
      }).catch(() => { if (!disposed) setError('Unable to render this chart.') })
    }
    return () => { disposed = true; finalize?.() }
  }, [chart, appearance])
  return <><Feedback error={error} loading={false} /><div className="chart" ref={container} aria-label={`${chart.title} chart`} /></>
}

export default function SavedChart({ chart }: { chart: Chart }) {
  const iframe = useRef<HTMLIFrameElement>(null)
  const send = () => iframe.current?.contentWindow?.postMessage({ rows: chart.rows }, '*')
  useEffect(() => { iframe.current?.contentWindow?.postMessage({ rows: chart.rows }, '*') }, [chart])
  if (isHtml(chart)) return <iframe ref={iframe} title={`${chart.title} chart`} sandbox="allow-scripts" srcDoc={sandboxDocument(chart.spec.html)} onLoad={send} className="html-chart" referrerPolicy="no-referrer" />
  return <VegaChart chart={chart} />
}
