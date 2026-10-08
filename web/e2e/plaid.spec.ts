import { test, expect } from '@playwright/test'
import { execFileSync } from 'node:child_process'

const live = process.env.LEDGERLIGHT_E2E_PLAID === 'sandbox'

test('offline link, sync, filters, recurring, balances and net worth at mobile width', async ({ page, request }) => {
  test.skip(live, 'Offline fake suite; live Sandbox has its own spec')
  // Reject all external browser requests: the fake must never load Plaid's iframe.
  await page.route('**/*', route => {
    if (new URL(route.request().url()).hostname !== '127.0.0.1') return route.abort()
    return route.continue()
  })
  expect((await request.post('/api/plaid/link-token')).ok()).toBeTruthy()
  expect((await request.post('/api/plaid/exchange', {
    data: { public_token: 'public-synthetic-ledgerlight' },
  })).ok()).toBeTruthy()
  expect((await request.post('/api/sync')).ok()).toBeTruthy()
  await page.setViewportSize({ width: 375, height: 812 })
  await page.goto('/')
  await expect(page.getByText('test mode', { exact: true })).toBeVisible()
  await expect(page.getByRole('region', { name: 'Net worth', exact: true }).locator('svg')).toBeVisible()
  await page.getByRole('link', { name: 'Transactions', exact: true }).click()
  await expect(page.getByText('Synthetic Coffee', { exact: false })).toBeVisible()
  await expect(page.getByText('Pending', { exact: true })).toBeVisible()
  await page.getByRole('searchbox', { name: 'Search' }).fill('Payroll')
  await page.getByRole('button', { name: 'Apply filters' }).click()
  await expect(page.getByRole('cell', { name: 'Synthetic Payroll' })).toBeVisible()
  await expect(page.getByText('Synthetic Coffee', { exact: false })).toHaveCount(0)
  await page.getByRole('searchbox', { name: 'Search' }).fill('no match')
  await page.getByRole('button', { name: 'Apply filters' }).click()
  await expect(page.getByText('No matching transactions.')).toBeVisible()
  await page.getByRole('searchbox', { name: 'Search' }).fill('')
  await page.getByLabel('Category', { exact: true }).fill('FOOD_AND_DRINK')
  await page.getByRole('combobox', { name: 'Account', exact: true }).selectOption({ label: 'Synthetic Checking' })
  await page.getByRole('button', { name: 'Apply filters' }).click()
  await expect(page.getByRole('cell', { name: 'Synthetic Coffee Pending' })).toBeVisible()
  await expect(page.getByRole('cell', { name: 'Synthetic Payroll' })).toHaveCount(0)
  await page.getByRole('link', { name: 'Recurring', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Synthetic Streaming' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Synthetic Payroll' })).toBeVisible()
  await expect(page.getByText('Next:', { exact: false }).first()).toBeVisible()
  await page.getByRole('link', { name: 'Accounts', exact: true }).click()
  await expect(page.locator('.account-balance').filter({ hasText: '$2,500.00' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Synthetic Bank', exact: true })).toBeVisible()
  await expect(page.getByText('Last sync:', { exact: false })).not.toContainText('Never')
  await page.getByRole('button', { name: 'Sync now' }).click()
  await expect(page.getByText('Sync complete.')).toBeVisible()
  await page.getByRole('button', { name: 'Link account', exact: true }).click()
  await expect(page.getByText('Account linked.', { exact: false })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy()
  await page.reload()
  await expect(page.getByRole('heading', { name: 'Accounts', exact: true })).toBeVisible()
})

test('live Plaid Sandbox link/exchange and eventually transactions and recurring', async ({ request, page }) => {
  test.skip(!live, 'Set LEDGERLIGHT_E2E_PLAID=sandbox and Sandbox credentials to opt in')
  test.setTimeout(660000)
  if (!process.env.PLAID_CLIENT_ID || !process.env.PLAID_SECRET) throw new Error('Sandbox credentials required')
  // All Plaid access, including sandbox token creation, stays in the client module.
  // Token is captured in memory, not echoed, saved as a fixture or put in a report.
  const root = process.env.LEDGERLIGHT_E2E_STORAGE
  if (!root) throw new Error('LEDGERLIGHT_E2E_STORAGE is required for isolated Sandbox storage')
  const publicToken = execFileSync('uv', ['run', 'python', '-c',
    'from ledgerlight.plaid_client import get_client; print(get_client().sandbox_public_token())'], {
    cwd: '..', encoding: 'utf8', env: {
      ...process.env, PLAID_ENV: 'sandbox', LEDGERLIGHT_FAKE_PLAID: '0',
      LEDGERLIGHT_DATA_DIR: `${root}/data`, LEDGERLIGHT_CONFIG_DIR: `${root}/config`,
    },
    stdio: ['ignore', 'pipe', 'ignore'],
  }).trim()
  const exchanged = await request.post('/api/plaid/exchange', { data: { public_token: publicToken } })
  expect(exchanged.status()).toBe(200)
  await expect.poll(async () => {
    const synced = await request.post('/api/sync')
    if (!synced.ok()) return false
    const transactions = await (await request.get('/api/transactions')).json()
    const recurring = await (await request.get('/api/recurring')).json()
    const status = await (await request.get('/api/sync/status')).json()
    return transactions.length > 0 && recurring.length > 0
      && status.items.every((item: { history_status: string }) => item.history_status === 'HISTORICAL_UPDATE_COMPLETE')
  }, { timeout: 600000, intervals: [2000, 5000, 10000] }).toBe(true)
  const history = await (await request.get('/api/sync/status')).json()
  console.log('Sandbox historical import complete; oldest dates:', history.items.map((item: { oldest_txn_date: string | null }) => item.oldest_txn_date))
  await page.goto('/#/accounts')
  await expect(page.getByText('test mode', { exact: true })).toHaveCount(0)
  await expect(page.getByRole('region', { name: 'Accounts ranked by balance' })).toBeVisible()
  await page.getByRole('link', { name: 'Transactions', exact: true }).click()
  await expect(page.locator('tbody tr').first()).toBeVisible()
  await page.getByRole('link', { name: 'Recurring', exact: true }).click()
  await expect(page.locator('.cards li').first()).toBeVisible()
})
