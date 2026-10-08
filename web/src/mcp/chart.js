import embed from 'vega-embed'

// Minimal MCP Apps JSON-RPC bridge. No tools/call capability or network access.
let view
let generation = 0
const send = message => parent.postMessage({ jsonrpc: '2.0', ...message }, '*')
const status = document.getElementById('status')
async function render(result) {
  const current = ++generation
  try {
    const chart = result.structuredContent || JSON.parse(result.content.find(item => item.type === 'text').text)
    document.getElementById('title').textContent = chart.title || 'Chart'
    view?.finalize()
    view = undefined
    document.getElementById('chart').replaceChildren()
    if (chart.spec?.kind === 'html') {
      status.textContent = 'HTML charts are available in the ledgerlight dashboard. This viewer renders Vega-Lite only.'
      return
    }
    // Never forward model-controlled URLs, transforms, expressions or config.
    const source = chart.spec || {}
    const encoding = Object.fromEntries(Object.entries(source.encoding || {})
      .filter(([key]) => ['x', 'y', 'theta', 'color'].includes(key))
      .map(([key, value]) => [key, {
        field: String(value.field || ''),
        type: value.type === 'quantitative' ? 'quantitative' : 'nominal',
        title: String(value.title || ''),
      }]))
    const spec = {
      mark: ['bar', 'line', 'area', 'arc'].includes(source.mark) ? source.mark : 'bar',
      encoding, width: 480, height: 280,
      data: { values: Array.isArray(chart.rows) ? chart.rows : [] },
    }
    const rendered = await embed('#chart', spec, { actions: false, renderer: 'svg' })
    if (generation !== current) { rendered.finalize(); return }
    view = rendered
    status.textContent = ''
    send({ method: 'ui/notifications/size-changed', params: { height: document.body.scrollHeight } })
  } catch {
    status.textContent = 'Unable to render chart. The tool result includes the spec, rows and dashboard link.'
  }
}
window.addEventListener('message', event => {
  if (event.source !== parent || event.data?.jsonrpc !== '2.0') return
  const message = event.data
  if (message.id === 'initialize' && message.result) {
    send({ method: 'ui/notifications/initialized', params: {} })
  } else if (message.method === 'ui/notifications/tool-result') {
    void render(message.params)
  } else if (message.method === 'ui/resource-teardown') {
    generation++
    view?.finalize()
    send({ id: message.id, result: {} })
  } else if (message.method === 'ping') {
    send({ id: message.id, result: {} })
  }
})
send({ id: 'initialize', method: 'ui/initialize', params: {
  appInfo: { name: 'ledgerlight chart', version: '1.0.0' },
  appCapabilities: {}, protocolVersion: '2026-01-26',
} })
