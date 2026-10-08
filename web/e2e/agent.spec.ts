import { test, expect, type Page } from '@playwright/test'
import { spawn } from 'node:child_process'
import { mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { createServer } from 'node:net'

async function ask(page: Page, text: string) {
  const drawer = page.getByLabel('Chat drawer')
  await drawer.getByLabel('Message', { exact: true }).fill(text)
  await drawer.getByRole('button', { name: 'Send', exact: true }).click()
  await expect(drawer.getByRole('button', { name: 'Send', exact: true })).toBeVisible()
  await expect(drawer.getByRole('alert')).toHaveCount(0)
}

test('agent moves live with Undo, saves and edits charts, confirms or cancels budgets, records speech and sandboxes HTML', async ({ page, request }) => {
  test.skip(process.env.LEDGERLIGHT_E2E_PLAID === 'sandbox', 'Offline fake only')
  await page.route('**/*', route => new URL(route.request().url()).hostname === '127.0.0.1' ? route.continue() : route.abort())
  await request.post('/api/plaid/exchange', { data: { public_token: 'public-synthetic-ledgerlight' } })
  await request.post('/api/sync')
  await request.get('/api/dashboard')
  await request.post('/api/dashboard/move', { data: { id: 'spending_vs_last_month', x: 6, y: 20 } })
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.goto('/')
  await expect(page.getByText('Live UI connected')).toBeVisible()
  await page.getByRole('button', { name: 'Chat', exact: true }).click()
  const drawer = page.getByLabel('Chat drawer')
  await ask(page, 'move dining vs last month to the top left')
  const card = page.locator('[data-card-id="spending_vs_last_month"]')
  await expect(card).toHaveAttribute('data-x', '0')
  await expect(card).toHaveAttribute('data-y', '0')
  await expect(drawer).toContainText('Moved card')
  await page.locator('.receipt').getByRole('button', { name: 'Undo', exact: true }).click()
  await expect(card).toHaveAttribute('data-x', '6')
  await expect(card).toHaveAttribute('data-y', '20')

  await ask(page, 'show spending by category')
  const preview = drawer.getByLabel('Chat chart').last()
  await expect(preview.locator('svg')).toBeVisible()
  await preview.getByRole('button', { name: 'Save', exact: true }).click()
  await expect(preview).toContainText('Saved to Home')
  await page.reload()
  const saved = page.getByRole('region', { name: 'Saved charts', exact: true }).getByRole('region', { name: 'Spending by category', exact: true }).last()
  await expect(saved.locator('svg')).toBeVisible()
  await saved.getByText('Edit chart · version 1').click()
  await saved.getByLabel('Chart title').fill('Spending by category edited')
  await saved.getByRole('button', { name: 'Save new version' }).click()
  const edited = page.getByRole('region', { name: 'Spending by category edited', exact: true })
  await expect(edited).toContainText('version 2')
  await edited.getByRole('button', { name: 'Load chart history' }).click()
  await expect(edited).toContainText('Version 1: Spending by category')
  await expect(edited).toContainText('Version 2: Spending by category edited')

  await page.getByRole('button', { name: 'Chat', exact: true }).click()
  await ask(page, 'set dining budget to 400')
  const confirm = drawer.getByLabel('Confirm change').last()
  await expect(confirm).toContainText('400')
  const before = await (await request.get('/api/budgets')).json()
  expect(before.some((b: { category: string; monthly_limit: number }) => b.category === 'Dining' && b.monthly_limit === 400)).toBeFalsy()
  await confirm.getByRole('button', { name: 'Confirm', exact: true }).click()
  await expect(confirm.getByRole('status')).toHaveText('Applied')
  await page.getByRole('link', { name: 'Budgets', exact: true }).click()
  await expect(page.locator('.cards li').filter({ has: page.getByRole('heading', { name: 'Dining', exact: true }) })).toContainText('of 400.00')
  await ask(page, 'set dining budget to 999')
  const cancel = drawer.getByLabel('Confirm change').last()
  await cancel.getByRole('button', { name: 'Cancel', exact: true }).click()
  await expect(cancel.getByRole('status')).toHaveText('Cancelled')
  const after = await (await request.get('/api/budgets')).json()
  expect(after.find((b: { category: string }) => b.category === 'Dining').monthly_limit).toBe(400)

  let agentRequests = 0
  page.on('request', r => { if (r.url().endsWith('/api/agent')) agentRequests++ })
  const microphone = drawer.getByRole('button', { name: 'Microphone' })
  await microphone.scrollIntoViewIfNeeded()
  await microphone.hover()
  await page.mouse.down()
  await expect(microphone).toHaveAttribute('aria-pressed', 'true')
  await page.waitForTimeout(200)
  await page.mouse.up()
  await expect(drawer.getByLabel('Message', { exact: true })).toHaveValue('Show spending by category')
  expect(agentRequests).toBe(0)

  await ask(page, 'show an html chart')
  const frame = drawer.locator('iframe').last()
  await expect(frame).toHaveAttribute('sandbox', 'allow-scripts')
  await expect(frame.contentFrame().locator('body')).toHaveAttribute('data-blocked', 'yes')
  await expect(frame.contentFrame().locator('#result')).toContainText('Rows:')
  expect(await frame.evaluate((element: HTMLIFrameElement) => {
    try { return element.contentWindow!.document.body.textContent } catch { return 'opaque-origin' }
  })).toBe('opaque-origin')
  await page.setViewportSize({ width: 375, height: 812 })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy()
})

test('saved provider selection updates the real header without environment override', async ({ page }) => {
  test.setTimeout(120_000)
  await page.route('**/*', route => new URL(route.request().url()).hostname === '127.0.0.1' ? route.continue() : route.abort())
  const directory = mkdtempSync(join(tmpdir(), 'ledgerlight-provider-'))
  const port = await new Promise<number>(resolve => {
    const socket = createServer().listen(0, '127.0.0.1', () => {
      const address = socket.address() as { port: number }
      socket.close(() => resolve(address.port))
    })
  })
  const env = { ...process.env, LEDGERLIGHT_DATA_DIR: join(directory, 'data'), LEDGERLIGHT_CONFIG_DIR: join(directory, 'config'), LEDGERLIGHT_FAKE_PLAID: '1' }
  delete env.LEDGERLIGHT_LLM_PROVIDER
  delete env.OPENAI_API_KEY
  delete env.ANTHROPIC_API_KEY
  const child = spawn('uv', ['run', 'ledgerlight', 'serve', '--port', String(port)], { cwd: '..', env, stdio: 'ignore' })
  try {
    await expect.poll(async () => {
      try {
        return (await fetch(`http://127.0.0.1:${port}/api/health`, { signal: AbortSignal.timeout(1000) })).status
      } catch { return 0 }
    }, { timeout: 60_000, message: 'Temporary provider server becomes healthy' }).toBe(200)
    await page.goto(`http://127.0.0.1:${port}/#/settings`)
    await expect(page.locator('.topbar .provider-chip')).toHaveText('Provider: local')
    await page.getByLabel('Provider', { exact: true }).selectOption('openai')
    await page.getByRole('button', { name: 'Save provider', exact: true }).click()
    await expect(page.locator('.topbar .provider-chip')).toHaveText('Provider: openai')
    await page.reload()
    await expect(page.locator('.topbar .provider-chip')).toHaveText('Provider: openai')
    const providerSelect = page.getByLabel('Provider', { exact: true })
    await expect(providerSelect).toHaveValue('openai')
    // Hold every real status response so neither consumer can refresh before
    // the next choice. Synchronize on saved data, not an exact request count:
    // identical GETs may be serialized/coalesced by the browser.
    let releaseStatus!: () => void
    const statusGate = new Promise<void>(resolve => { releaseStatus = resolve })
    let heldStatus: { provider: string; model: string } | undefined
    await page.route('**/api/llm/status', async route => {
      const response = await route.fetch({ timeout: 15_000 })
      heldStatus = await response.json()
      await statusGate
      await route.fulfill({ response })
    })
    try {
      await providerSelect.selectOption('claude')
      await page.getByRole('button', { name: 'Save provider', exact: true }).click()
      await expect.poll(() => heldStatus?.provider, {
        timeout: 15_000, message: 'A held status response reflects the saved Claude provider',
      }).toBe('claude')
      await expect(providerSelect).toBeEnabled()
      await providerSelect.selectOption('local')
    } finally {
      releaseStatus()
    }
    await expect(page.locator('.topbar .provider-chip')).toHaveText('Provider: claude')
    // The header alone does not prove Settings has consumed its delayed read.
    await expect(page.getByRole('region', { name: 'Agent provider', exact: true })).toContainText(heldStatus!.model)
    await expect(providerSelect).toHaveValue('local')
    await page.unroute('**/api/llm/status')
    await page.getByRole('button', { name: 'Save provider', exact: true }).click()
    await expect(page.locator('.topbar .provider-chip')).toHaveText('Provider: local')
    await page.reload()
    await expect(page.locator('.topbar .provider-chip')).toHaveText('Provider: local')
    await expect(providerSelect).toHaveValue('local')
    await page.getByRole('button', { name: 'Chat', exact: true }).click()
    await expect(page.getByRole('button', { name: 'Microphone' })).toHaveCount(0)
  } finally {
    if (!page.isClosed()) await page.goto('about:blank').catch(() => {})
    child.kill('SIGTERM')
    await new Promise<void>(resolve => {
      const timer = setTimeout(() => { child.kill('SIGKILL'); resolve() }, 5000)
      if (child.exitCode !== null) { clearTimeout(timer); resolve() }
      else child.once('exit', () => { clearTimeout(timer); resolve() })
    })
    rmSync(directory, { recursive: true, force: true })
  }
})
