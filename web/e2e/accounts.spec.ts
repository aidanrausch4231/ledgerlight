import { test, expect } from '@playwright/test'
import { execFileSync } from 'node:child_process'

function syntheticSql(sql: string) {
  const root = process.env.LEDGERLIGHT_E2E_STORAGE
  if (!root) throw new Error('Isolated test storage required')
  execFileSync('uv', ['run', 'python', '-c', 'import sys; from ledgerlight.db import connect\nwith connect() as db: db.executescript(sys.argv[1])', sql], {
    cwd: '..', encoding: 'utf8', env: { ...process.env, LEDGERLIGHT_DATA_DIR: `${root}/data`, LEDGERLIGHT_CONFIG_DIR: `${root}/config` },
  })
}

test('ranked account ledger, accessible ring, history honesty and phone layout', async ({ page, request }) => {
  test.skip(process.env.LEDGERLIGHT_E2E_PLAID === 'sandbox', 'Offline fake only')
  await page.route('**/*', route => new URL(route.request().url()).hostname === '127.0.0.1' ? route.continue() : route.abort())
  expect((await request.post('/api/plaid/exchange', { data: { public_token: 'public-synthetic-ledgerlight' } })).ok()).toBeTruthy()
  expect((await request.post('/api/sync')).ok()).toBeTruthy()
  syntheticSql(`INSERT INTO accounts (id,name,balance,type,mask) VALUES
    ('stage8-fund','Synthetic Fund',20000,'investment','8888'),
    ('stage8-empty','Synthetic Empty',0,'investment','9999');`)
  try {
    await page.goto('/#/accounts')
    const ring = page.getByRole('img', { name: /^Holdings:/ })
    await expect(ring).toBeVisible()
    await expect(ring).toHaveAttribute('aria-label', /cash, .* invested; owed/)
    await expect(page.locator('.account-group-heading h2')).toHaveText(['Investments', 'Cash', 'Owed'])
    await expect(page.locator('.account-row').first()).toContainText('Synthetic Fund')
    await expect(page.locator('.account-rank').first()).toHaveText('1')
    await expect(page.locator('.owed .account-balance')).toHaveText('−$100.00')
    await expect(page.locator('.owed .account-note')).toHaveText('$900.00 left')
    await expect(page.locator('.account-empty')).toContainText('Synthetic Empty ••9999')
    const light = await ring.locator('circle').nth(1).evaluate(el => getComputedStyle(el).stroke)
    await page.evaluate(() => document.documentElement.dataset.theme = 'dark')
    const dark = await ring.locator('circle').nth(1).evaluate(el => getComputedStyle(el).stroke)
    expect(dark).not.toBe(light)
    await page.setViewportSize({ width: 390, height: 844 })
    await expect(ring).toHaveCSS('width', '104px')
    await expect(page.locator('.account-phone-meta').first()).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
    const button = page.getByRole('button', { name: 'Link account', exact: true })
    await expect(button).toBeVisible()
    expect((await button.boundingBox())!.width).toBe(358)
    // Explicit invalidation updates the shared read without a page reload.
    syntheticSql("UPDATE accounts SET balance=21000 WHERE id='stage8-fund'")
    await page.evaluate(() => window.dispatchEvent(new Event('ledgerlight-change')))
    await expect(page.locator('.account-balance').first()).toHaveText('$21,000.00')
    // Real API-derived short-history label, with fixed synthetic link/date evidence.
    syntheticSql("UPDATE plaid_items SET created_at='2026-10-03 12:00:00', history_days=365, history_status='HISTORICAL_UPDATE_COMPLETE', oldest_txn_date='2026-07-02'")
    await expect(page.getByText('History from Jul 2, 2026 — Synthetic Bank sent less than the 12 months requested')).toBeVisible()
    await expect(page.getByText('Full year imported', { exact: true })).toHaveCount(0)
    syntheticSql("UPDATE plaid_items SET history_days=540, oldest_txn_date='2025-04-11'")
    await expect(page.getByText('Full 540 days imported', { exact: true })).toBeVisible()
    await page.goto('/#/')
    await expect(page.getByRole('combobox', { name: 'Add to Home', exact: true })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Add', exact: true })).toBeVisible()
  } finally {
    syntheticSql("DELETE FROM accounts WHERE id IN ('stage8-fund','stage8-empty'); UPDATE plaid_items SET history_days=365;")
    await request.post('/api/sync')
  }
})

test('zero-held overview shows only the track and empty account names', async ({ page }) => {
  await page.route('**/api/accounts/overview*', route => route.fulfill({ json: {
    net_worth: 0, held: 0, owed: 0, cash_total: 0, invested_total: 0, cash_share: 0, invested_share: 0, owed_ratio: 0,
    groups: [], empty: [{ id: 'empty', name: 'Synthetic Empty', institution: 'Manual', mask: null }],
  } }))
  await page.goto('/#/accounts')
  await expect(page.getByRole('img', { name: /^Holdings:/ }).locator('circle')).toHaveCount(1)
  await expect(page.locator('.account-empty')).toHaveText('+ 1 empty account · Synthetic Empty')
})
