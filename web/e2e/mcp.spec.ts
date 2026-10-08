import { test, expect } from '@playwright/test'
import { execFileSync } from 'node:child_process'

function mcp(name: string, args: Record<string, unknown> = {}) {
  if (!process.env.LEDGERLIGHT_E2E_STORAGE) throw new Error('Isolated storage required')
  return JSON.parse(execFileSync('uv', ['run', 'python', 'web/e2e/mcp_client.py', name, JSON.stringify(args)], {
    cwd: '..', encoding: 'utf8', env: process.env, maxBuffer: 4 * 1024 * 1024,
  }))
}

test('MCP moves a live card and proposals require user confirmation on durable routes', async ({ page, request }) => {
  test.skip(process.env.LEDGERLIGHT_E2E_PLAID === 'sandbox', 'Offline synthetic data only')
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.goto('/')
  await expect(page.getByText('Live UI connected')).toBeVisible()
  await page.evaluate(() => { document.body.dataset.noReload = 'mcp-live' })
  const move = mcp('dashboard_move', { id: 'cashflow', x: 0, y: 35 })
  expect(move.event.actor).toBe('mcp')
  const card = page.locator('[data-card-id="cashflow"]')
  await expect(card).toHaveAttribute('data-x', '0')
  await expect(card).toHaveAttribute('data-y', '35')
  await expect(page.locator('.receipt')).toContainText('MCP moved Cash flow')
  await expect(page.locator('body')).toHaveAttribute('data-no-reload', 'mcp-live')

  const proposal = mcp('propose_budgets_set', { category: 'MCP synthetic budget', monthly_limit: '321' })
  const budgets = async () => (await (await request.get('/api/budgets')).json()) as { category: string; monthly_limit: number }[]
  expect((await budgets()).find(b => b.category === 'MCP synthetic budget')).toBeUndefined()
  await page.getByRole('link', { name: 'Proposals', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Pending proposals' })).toBeVisible()
  await page.getByRole('link', { name: proposal.summary, exact: true }).click()
  await expect(page).toHaveURL(new RegExp(`#/proposals/${proposal.proposal_id}$`))
  await page.reload()
  await expect(page.getByRole('heading', { name: 'Review proposal' })).toBeVisible()
  await page.getByRole('button', { name: 'Confirm', exact: true }).click()
  await expect(page.getByRole('status').filter({ hasText: /^Applied$/ })).toBeVisible()
  expect((await budgets()).find(b => b.category === 'MCP synthetic budget')?.monthly_limit).toBe(321)
  await page.reload()
  await expect(page.getByRole('status').filter({ hasText: /^Applied$/ })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Confirm', exact: true })).toHaveCount(0)

  const cancel = mcp('propose_budgets_set', { category: 'MCP synthetic cancelled', monthly_limit: '999' })
  await page.goto(`/#/proposals/${cancel.proposal_id}`)
  await page.getByRole('button', { name: 'Cancel', exact: true }).click()
  await expect(page.getByRole('status').filter({ hasText: /^Cancelled$/ })).toBeVisible()
  await page.getByRole('link', { name: 'All pending proposals' }).click()
  await expect(page.getByRole('link', { name: cancel.summary, exact: true })).toHaveCount(0)
  expect((await budgets()).find(b => b.category === 'MCP synthetic cancelled')).toBeUndefined()
  await page.goto('/#/proposals/missing-proposal')
  await expect(page.getByRole('alert').filter({ hasText: 'Proposal not found' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Confirm', exact: true })).toHaveCount(0)
})

test('MCP Apps bundle renders offline using the host bridge and blocks network', async ({ page }) => {
  test.skip(process.env.LEDGERLIGHT_E2E_PLAID === 'sandbox', 'Offline synthetic data only')
  const external: string[] = []
  page.on('request', request => { if (!request.url().startsWith('http://127.0.0.1')) external.push(request.url()) })
  await page.route('**/*', route => new URL(route.request().url()).hostname === '127.0.0.1' ? route.continue() : route.abort())
  await page.goto('/')
  const resource = mcp('resource')
  const chart = mcp('chart_preview', { title: 'Synthetic Apps chart', sql: "SELECT 'Synthetic apples' AS label, 3 AS value", type: 'bar' })
  await page.evaluate(html => {
    window.addEventListener('message', event => {
      if (event.data?.method === 'ui/initialize') {
        ;(event.source as Window).postMessage({ jsonrpc: '2.0', id: event.data.id, result: { protocolVersion: '2026-01-26', hostCapabilities: {}, hostInfo: { name: 'test-host', version: '1' } } }, '*')
      }
      if (event.data?.method === 'ui/notifications/initialized') document.body.dataset.appReady = 'true'
    })
    const frame = document.createElement('iframe')
    frame.id = 'mcp-app'
    frame.title = 'MCP chart'
    frame.setAttribute('sandbox', 'allow-scripts')
    frame.srcdoc = html
    document.body.appendChild(frame)
  }, resource.html)
  await expect(page.locator('body')).toHaveAttribute('data-app-ready', 'true')
  await page.evaluate(chart => {
    document.querySelector<HTMLIFrameElement>('#mcp-app')!.contentWindow!.postMessage({
      jsonrpc: '2.0', method: 'ui/notifications/tool-result', params: { structuredContent: chart },
    }, '*')
  }, chart)
  const frame = page.frameLocator('#mcp-app')
  await expect(frame.getByRole('heading', { name: 'Synthetic Apps chart' })).toBeVisible()
  await expect(frame.locator('svg')).toBeVisible()
  await expect(frame.locator('svg')).toContainText('Synthetic apples')
  const child = page.frames().find(frame => frame.url() === 'about:srcdoc')!
  const security = await child.evaluate(async () => {
    let networkBlocked = false, parentBlocked = false
    try { await fetch('https://example.invalid/mcp-app-must-not-connect') } catch { networkBlocked = true }
    try { void parent.document.body } catch { parentBlocked = true }
    return { networkBlocked, parentBlocked }
  })
  expect(security).toEqual({ networkBlocked: true, parentBlocked: true })
  expect(external).toEqual([])
})
