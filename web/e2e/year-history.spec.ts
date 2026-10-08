import { test, expect } from '@playwright/test'
import { execFileSync } from 'node:child_process'

test('fake Link shows progress then full year; relink preserves local annotations', async ({ page, request }) => {
  test.skip(process.env.LEDGERLIGHT_E2E_PLAID === 'sandbox', 'Offline fake only')
  test.setTimeout(120000)
  const root = process.env.LEDGERLIGHT_E2E_STORAGE
  if (!root) throw new Error('Isolated test storage required')
  const cli = (...args: string[]) => JSON.parse(execFileSync('uv', ['run', 'ledgerlight', '--json', ...args], {
    cwd: '..', encoding: 'utf8', env: { ...process.env, LEDGERLIGHT_DATA_DIR: `${root}/data`, LEDGERLIGHT_CONFIG_DIR: `${root}/config`, LEDGERLIGHT_FAKE_PLAID: '1', LEDGERLIGHT_TODAY: '2026-03-15' },
  }))
  for (const item of await (await request.get('/api/plaid/items')).json()) {
    expect((await request.post(`/api/plaid/items/${item.id}/remove`)).ok()).toBeTruthy()
  }
  cli('settings', 'set', 'history_days', '90')
  await page.goto('/#/accounts')
  await page.getByRole('button', { name: 'Link account', exact: true }).click()
  await expect(page.getByText('Account linked.', { exact: true })).toBeVisible()
  cli('settings', 'set', 'history_days', '365')
  await expect(page.getByText('Linked with 90 days of history — relink to fetch a full year')).toBeVisible()
  const row = (await (await request.get('/api/transactions?search=Coffee')).json())[0]
  cli('txn', 'note', row.id, 'Synthetic relink note')
  cli('txn', 'tag', row.id, 'history-kept')
  page.once('dialog', dialog => dialog.accept())
  await page.getByRole('button', { name: 'Relink', exact: true }).click()
  await expect(page.getByText('Importing your last 12 months…', { exact: true })).toBeVisible()
  await expect(page.getByText(/transactions · Oldest date:/)).toBeVisible()
  // No manual sync: the server's real 60-second worker finishes the import.
  await expect(page.getByText('Full year imported', { exact: true })).toBeVisible({ timeout: 75000 })
  await expect(page.getByText('365 transactions · Oldest date: 2025-03-16')).toBeVisible()
  const kept = (await (await request.get('/api/transactions?search=Coffee')).json())[0]
  expect(kept.note).toBe('Synthetic relink note')
  expect(kept.tags).toContain('history-kept')
  await page.getByRole('link', { name: 'Transactions', exact: true }).click()
  await page.getByLabel('Until', { exact: true }).fill('2025-03-16')
  await page.getByRole('button', { name: 'Apply filters', exact: true }).click()
  await expect(page.getByRole('cell', { name: '2025-03-16', exact: true })).toBeVisible()
})

test('chat client timeout clears Working and allows retry', async ({ page }) => {
  test.skip(process.env.LEDGERLIGHT_E2E_PLAID === 'sandbox', 'Offline fake only')
  await page.clock.install()
  let release!: () => void
  const held = new Promise<void>(resolve => { release = resolve })
  await page.route('**/api/agent', async route => {
    await held
    await route.abort().catch(() => {})
  })
  await page.goto('/')
  await page.getByRole('button', { name: 'Chat', exact: true }).click()
  await page.getByRole('textbox', { name: 'Message', exact: true }).fill('how much coffee')
  await page.getByRole('button', { name: 'Send', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Working…', exact: true })).toBeVisible()
  await page.clock.fastForward(90001)
  await expect(page.getByRole('alert')).toContainText('Please retry your message')
  await expect(page.getByText('Working…', { exact: true })).toHaveCount(0)
  release()
  await page.unroute('**/api/agent')
  await page.getByRole('textbox', { name: 'Message', exact: true }).fill('how much coffee')
  await page.getByRole('button', { name: 'Send', exact: true }).click()
  await expect(page.getByRole('region', { name: 'Answer', exact: true })).toBeVisible()
  await expect(page.getByText('Working…', { exact: true })).toHaveCount(0)
})
