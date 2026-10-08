import { test, expect, type APIRequestContext } from '@playwright/test'

const dollars = (value: number) => `${value < 0 ? '−' : ''}$${Math.abs(value).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`

async function todayNetWorth(request: APIRequestContext) {
  const rows: { date: string; total: number }[] = await (await request.get('/api/networth?days=1')).json()
  return rows[0]?.total ?? 0
}

async function removeAllManual(request: APIRequestContext) {
  for (const kind of ['manual', 'holdings']) {
    const rows: { id: string }[] = await (await request.get(`/api/${kind}`)).json()
    for (const row of rows) await request.delete(`/api/${kind}/${row.id}`)
  }
}

test('add a crypto holding and a student loan; groups, net worth, edit, remove and phone Chat clearance', async ({ page, request }) => {
  test.skip(process.env.LEDGERLIGHT_E2E_PLAID === 'sandbox', 'Offline fake prices only')
  // Fake prices only: nothing may leave loopback.
  await page.route('**/*', route => new URL(route.request().url()).hostname === '127.0.0.1' ? route.continue() : route.abort())
  expect((await request.get('/api/status')).ok()).toBeTruthy()
  expect((await (await request.get('/api/status')).json()).fake_prices).toBe(true)
  const before = (await (await request.get('/api/accounts/overview')).json()).net_worth as number
  const historyBefore = await todayNetWorth(request)
  try {
    await page.goto('/#/accounts')
    await page.getByRole('button', { name: 'Add manually' }).click()
    let form = page.getByRole('form', { name: 'Add manually' })
    await form.getByLabel('Kind').selectOption('crypto')
    await form.getByLabel('Symbol').fill('btc')
    // The resolved coin is shown before saving (highest market-cap rank).
    await expect(form.getByText('Coin: Bitcoin (bitcoin)')).toBeVisible()
    await form.getByLabel('Quantity').fill('0.5')
    await form.getByRole('button', { name: 'Add account' }).click()
    await expect(page.getByText('Added Bitcoin (BTC).')).toBeVisible()
    const crypto = page.locator('.account-group.crypto')
    await expect(crypto.locator('h2')).toHaveText('Crypto')
    await expect(crypto.locator('.account-row')).toContainText('0.5 BTC × $60,000.00')
    await expect(crypto.locator('.account-row')).toContainText('+1.50% 24h')
    await expect(crypto.locator('.account-balance')).toHaveText('$30,000.00')

    await page.getByRole('button', { name: 'Add manually' }).click()
    form = page.getByRole('form', { name: 'Add manually' })
    await expect(form.getByLabel('Kind')).toHaveValue('student_loan')
    await form.getByLabel('Name').fill('Synthetic Student Loan')
    await form.getByLabel('Amount owed').fill('12000')
    await form.getByLabel('APR (%)').fill('5.5')
    await form.getByLabel('Monthly payment').fill('200')
    await form.getByRole('button', { name: 'Add account' }).click()
    const loan = page.locator('.account-group.owed .account-row').filter({ hasText: 'Synthetic Student Loan' })
    await expect(loan.locator('.account-balance')).toHaveText('−$12,000.00')
    await expect(loan).toContainText('Manual')
    await expect(loan).toContainText('5.5% APR')

    const overview = await (await request.get('/api/accounts/overview')).json()
    expect(overview.net_worth).toBeCloseTo(before + 30000 - 12000, 2)
    await expect(page.locator('.account-worth-number')).toHaveText(dollars(overview.net_worth))
    expect(await todayNetWorth(request)).toBeCloseTo(historyBefore + 18000, 2)

    // Inline edit, then inline (non-dialog) remove confirmation.
    await page.getByRole('button', { name: 'Edit Synthetic Student Loan' }).click()
    const edit = page.getByRole('form', { name: 'Edit Synthetic Student Loan' })
    await edit.getByLabel('Amount owed').fill('11000')
    await edit.getByRole('button', { name: 'Save changes' }).click()
    await expect(loan.locator('.account-balance')).toHaveText('−$11,000.00')

    // Phone: right-aligned balances never sit under the floating Chat button.
    await page.setViewportSize({ width: 390, height: 844 })
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
    const chat = page.getByRole('button', { name: 'Chat', exact: true })
    const balances = page.locator('.account-balance')
    const count = await balances.count()
    expect(count).toBeGreaterThan(1)
    for (let index = 0; index < count; index++) {
      const balance = balances.nth(index)
      await balance.scrollIntoViewIfNeeded()
      for (const align of ['start', 'end'] as const) {
        await balance.evaluate((el, block) => el.scrollIntoView({ block }), align)
        const a = (await balance.boundingBox())!
        const b = (await chat.boundingBox())!
        const overlap = a.x < b.x + b.width && b.x < a.x + a.width && a.y < b.y + b.height && b.y < a.y + a.height
        expect(overlap, `balance ${index} (${align}) overlaps Chat`).toBe(false)
      }
    }
    await expect(page.locator('.account-group.crypto .account-holding')).toBeVisible()

    page.on('dialog', () => { throw new Error('Remove must not use a browser dialog') })
    await page.getByRole('button', { name: 'Remove Bitcoin (BTC)' }).click()
    await page.getByRole('group', { name: 'Confirm removing Bitcoin (BTC)' }).getByRole('button', { name: 'Confirm remove' }).click()
    await expect(page.locator('.account-group.crypto')).toHaveCount(0)
    expect(await (await request.get('/api/holdings')).json()).toEqual([])
  } finally {
    await removeAllManual(request)
  }
})
