import type { Chart, HtmlSpec } from './types'

export const htmlCsp = "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; connect-src 'none'; form-action 'none'; base-uri 'none'"
export const sandboxDocument = (html: string) => `<meta http-equiv="Content-Security-Policy" content="${htmlCsp}">${html}`
export const isHtml = (chart: Chart): chart is Chart & { spec: HtmlSpec } => 'kind' in chart.spec && chart.spec.kind === 'html'
export const chartInput = (chart: Chart) => ({ title: chart.title, sql: chart.sql || '', type: isHtml(chart) ? 'html' : String((chart.spec as { mark: string }).mark), html: isHtml(chart) ? chart.spec.html : '' })
