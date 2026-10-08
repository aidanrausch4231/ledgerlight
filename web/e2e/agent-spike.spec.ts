import { test, expect } from '@playwright/test'

test('AG-UI HttpAgent executes browser navigation and returns its result', async ({ page }) => {
  test.skip(process.env.LEDGERLIGHT_E2E_PLAID === 'sandbox', 'Offline fake only')
  await page.route('**/*', route => new URL(route.request().url()).hostname === '127.0.0.1' ? route.continue() : route.abort())
  const requests: { tools: { name: string }[]; messages: { role: string; content?: string }[] }[] = []
  page.on('request', r => { if (r.url().endsWith('/api/agent')) requests.push(r.postDataJSON()) })
  await page.goto('/')
  await page.getByRole('button', { name: 'Chat', exact: true }).click()
  await page.getByLabel('Message', { exact: true }).fill('open budgets')
  await page.getByRole('button', { name: 'Send', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Budgets', exact: true })).toBeVisible()
  await expect(page.getByLabel('Chat drawer')).toContainText('Navigation result received.')
  expect(requests).toHaveLength(2)
  expect(requests[0].tools.some(t => t.name === 'ui_navigate')).toBeTruthy()
  expect(requests[1].messages.some(m => m.role === 'tool' && m.content?.includes('budgets'))).toBeTruthy()
})
