import { test, expect } from '@playwright/test'
import { execFileSync } from 'node:child_process'

function cli(...args: string[]) {
  const root = process.env.LEDGERLIGHT_E2E_STORAGE
  if (!root) throw new Error('Isolated test storage is required')
  return JSON.parse(execFileSync('uv', ['run', 'ledgerlight', '--json', ...args], {
    cwd: '..', encoding: 'utf8', env: { ...process.env, LEDGERLIGHT_DATA_DIR: `${root}/data`, LEDGERLIGHT_CONFIG_DIR: `${root}/config`, LEDGERLIGHT_TODAY: '2026-03-15' },
  }))
}

test('CLI events update one live stream, undo, filters, highlight and persisted drag', async ({ page, request }) => {
  // This full workflow launches many real CLI processes and now renders saved
  // answer cards too; allow startup/render time without weakening assertions.
  test.setTimeout(60_000)
  test.skip(process.env.LEDGERLIGHT_E2E_PLAID === 'sandbox', 'Synthetic offline data only')
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  let streams = 0
  page.on('request', r => { if (r.url().includes('/api/events?')) streams++ })
  await page.route('**/*', route => new URL(route.request().url()).hostname === '127.0.0.1' ? route.continue() : route.abort())
  await request.post('/api/plaid/exchange', { data: { public_token: 'public-synthetic-ledgerlight' } })
  await request.post('/api/sync')
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.goto('/')
  await expect(page.getByText('Live UI connected')).toBeVisible()
  await page.evaluate(() => { document.body.dataset.noReload = 'still-here' })
  const initial = cli('dashboard', 'list')
  const original = initial.cards.find((c: { id: string }) => c.id === 'cashflow')
  const cash = page.locator('[data-card-id="cashflow"]')
  cli('dashboard', 'move', 'cashflow', '--x', '0', '--y', '0')
  await expect(cash).toHaveAttribute('data-x', '0')
  await expect(cash).toHaveAttribute('data-y', '0')
  await expect(cash).toHaveClass(/agent-marked/)
  await expect(page.locator('.receipt')).toContainText('CLI moved Cash flow')
  await page.locator('.receipt').getByRole('button', { name: 'Undo', exact: true }).click()
  await expect(cash).toHaveAttribute('data-x', String(original.x))
  await expect(cash).toHaveAttribute('data-y', String(original.y))
  await expect(cash).not.toHaveClass(/agent-marked/)
  await expect(page.locator('.receipt')).toHaveCount(0)

  // A CLI undo is itself a non-user change with a reversible receipt.
  cli('dashboard', 'undo')
  await expect(cash).toHaveAttribute('data-x', '0')
  await expect(cash).toHaveAttribute('data-y', '0')
  await expect(page.locator('.receipt')).toContainText('CLI undid changes to dashboard')
  await page.locator('.receipt').getByRole('button', { name: 'Undo', exact: true }).click()
  await expect(cash).toHaveAttribute('data-x', String(original.x))
  await expect(cash).toHaveAttribute('data-y', String(original.y))
  await expect(page.locator('.receipt')).toHaveCount(0)

  const added = cli('dashboard', 'add', 'top_merchants', '--x', '0', '--y', '0')
  const newCard = page.locator(`[data-card-id="${added.id}"]`)
  await expect(newCard).toBeVisible()
  cli('dashboard', 'resize', added.id, '--w', '4', '--h', '6')
  await expect(newCard).toHaveAttribute('data-w', '4')
  await expect(newCard).toHaveAttribute('data-h', '6')
  cli('dashboard', 'remove', added.id)
  await expect(newCard).toHaveCount(0)
  await page.locator('.receipt').getByRole('button', { name: 'Undo', exact: true }).click()
  await expect(newCard).toBeVisible()
  cli('dashboard', 'remove', added.id)
  await expect(newCard).toHaveCount(0)

  cli('ui', 'navigate', 'transactions')
  await expect(page.getByRole('heading', { name: 'Transactions', exact: true })).toBeVisible()
  cli('ui', 'filter', 'transactions', 'search=Payroll')
  await expect(page.getByRole('searchbox', { name: 'Search' })).toHaveValue('Payroll')
  await expect(page.getByRole('cell', { name: 'Synthetic Payroll', exact: true })).toBeVisible()
  await expect(page.getByRole('cell', { name: /Synthetic Coffee/ })).toHaveCount(0)
  await page.locator('.receipt').getByRole('button', { name: 'Undo', exact: true }).click()
  await expect(page.getByRole('searchbox', { name: 'Search' })).toHaveValue('')
  cli('ui', 'highlight', 'page:transactions')
  await expect(page.locator('[data-ui-id="page:transactions"]')).toHaveClass(/ui-highlight/)
  await expect(page.locator('[data-ui-id="page:transactions"]')).not.toHaveClass(/ui-highlight/, { timeout: 4000 })
  cli('ui', 'filter', 'transactions', 'search=Payroll')
  await expect(page.getByRole('searchbox', { name: 'Search' })).toHaveValue('Payroll')
  cli('ui', 'clear')
  await expect(page.getByRole('searchbox', { name: 'Search' })).toHaveValue('')
  await expect(page.locator('body')).toHaveAttribute('data-no-reload', 'still-here')
  expect(streams).toBe(1)

  cli('ui', 'navigate', 'home')
  await expect(page.getByRole('heading', { name: 'Home', exact: true })).toBeVisible()
  // Start at a different row with the same column: x alone cannot prove that
  // the next SSE move arrived. Previous specs can also leave this card far down.
  cli('dashboard', 'move', 'cashflow', '--x', '0', '--y', '35')
  await expect(cash).toHaveAttribute('data-x', '0')
  await expect(cash).toHaveAttribute('data-y', '35')
  cli('dashboard', 'move', 'cashflow', '--x', '0', '--y', '0')
  await expect(cash).toHaveAttribute('data-x', '0')
  await expect(cash).toHaveAttribute('data-y', '0')
  const handle = cash.getByRole('button', { name: 'Drag Cash flow', exact: true })
  // Wait for actual stability/hit testing after SSE, not a fixed animation sleep.
  // Hover also scrolls the final handle position into the viewport.
  await handle.hover()
  const beforeDrag = (await (await request.get('/api/dashboard')).json()).version
  const box = (await handle.boundingBox())!
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
  await page.mouse.down()
  await page.mouse.move(box.x + box.width / 2 + 180, box.y + box.height / 2 + 132, { steps: 20 })
  await page.mouse.up()
  await expect.poll(async () => (await (await request.get('/api/dashboard')).json()).version).toBeGreaterThan(beforeDrag)
  const saved = (await (await request.get('/api/dashboard')).json()).cards.find((c: { id: string }) => c.id === 'cashflow')
  expect(saved.x !== 0 || saved.y !== 0).toBeTruthy()
  await page.reload()
  await expect(cash).toHaveAttribute('data-x', String(saved.x))
  await expect(cash).toHaveAttribute('data-y', String(saved.y))
  expect(errors).toEqual([])
})

test('Tide Table system/dark theme, keyboard controls and every page at 375px', async ({ page }) => {
  test.skip(process.env.LEDGERLIGHT_E2E_PLAID === 'sandbox', 'Synthetic offline data only')
  await page.emulateMedia({ colorScheme: 'dark', reducedMotion: 'reduce' })
  await page.setViewportSize({ width: 375, height: 812 })
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Home', exact: true })).toBeVisible()
  expect(await page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue('--ground').trim())).toBe('#071620')
  await page.getByRole('button', { name: 'Toggle dark mode' }).click()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light')
  await page.getByRole('button', { name: 'Toggle dark mode' }).click()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
  await page.reload()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
  await page.getByRole('button', { name: 'System theme' }).click()
  await expect(page.locator('html')).not.toHaveAttribute('data-theme')
  for (const name of ['Home', 'Transactions', 'Recurring', 'Accounts', 'Budgets', 'Net worth', 'Rules', 'Goals', 'Bills', 'Settings']) {
    await page.getByRole('link', { name, exact: true }).click()
    await expect(page.getByRole('heading', { name, exact: true }).first()).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy()
  }
  await page.getByRole('link', { name: 'Home', exact: true }).click()
  const card = page.locator('[data-card-id="cashflow"]')
  await card.getByText('Card controls', { exact: true }).focus()
  await page.keyboard.press('Enter')
  await card.getByLabel('Column', { exact: true }).fill('0')
  await card.getByLabel('Row', { exact: true }).fill('40')
  await card.getByRole('button', { name: 'Move card', exact: true }).focus()
  await page.keyboard.press('Enter')
  await expect(card).toHaveAttribute('data-y', '40')
  await page.reload()
  await expect(card).toHaveAttribute('data-y', '40')
})
