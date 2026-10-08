import { test, expect, type APIRequestContext } from '@playwright/test'

type ManualRow = { id: string; name: string; payment_match: string | null; payment_match_since: string | null }

async function manualByName(request: APIRequestContext, name: string) {
  const rows: ManualRow[] = await (await request.get('/api/manual')).json()
  return rows.find(row => row.name === name)
}

test('set a payment match on a manual loan; it persists, shows on the row and refuses auto paydown', async ({ page, request }) => {
  test.skip(process.env.LEDGERLIGHT_E2E_PLAID === 'sandbox', 'Offline fixed date only')
  await page.route('**/*', route => new URL(route.request().url()).hostname === '127.0.0.1' ? route.continue() : route.abort())
  page.on('dialog', () => { throw new Error('Payment matching must not use a browser dialog') })
  const name = 'Synthetic Sample plan'
  try {
    await page.goto('/#/accounts')
    await page.getByRole('button', { name: 'Add manually' }).click()
    const form = page.getByRole('form', { name: 'Add manually' })
    await form.getByLabel('Kind').selectOption('personal_loan')
    await form.getByLabel('Name').fill(name)
    await form.getByLabel('Amount owed').fill('750')
    await form.getByLabel('Pays down from transactions matching').fill('ACME')
    await form.getByRole('button', { name: 'Add account' }).click()
    const row = page.locator('.account-group.owed .account-row').filter({ hasText: name })
    await expect(row).toContainText('Matches “ACME”, no payments yet')
    // Since defaults to the day the match is set (the offline server's fixed date).
    expect(await manualByName(request, name)).toMatchObject({ payment_match: 'ACME', payment_match_since: '2026-03-15' })

    // Edit: change the text and the since date, then reload and see both persist.
    await row.getByRole('button', { name: `Edit ${name}` }).click()
    let edit = page.getByRole('form', { name: `Edit ${name}` })
    await expect(edit.getByLabel('Pays down from transactions matching')).toHaveValue('ACME')
    await expect(edit.getByLabel('Matching since')).toHaveValue('2026-03-15')
    await edit.getByLabel('Pays down from transactions matching').fill('ACME PAYLATER')
    await edit.getByLabel('Matching since').fill('2026-03-01')
    await edit.getByRole('button', { name: 'Save changes' }).click()
    await expect(row).toContainText('Matches “ACME PAYLATER”, no payments yet')
    await page.reload()
    await expect(row).toContainText('Matches “ACME PAYLATER”, no payments yet')
    await row.getByRole('button', { name: `Edit ${name}` }).click()
    edit = page.getByRole('form', { name: `Edit ${name}` })
    await expect(edit.getByLabel('Pays down from transactions matching')).toHaveValue('ACME PAYLATER')
    await expect(edit.getByLabel('Matching since')).toHaveValue('2026-03-01')

    // One mechanism per loan: auto paydown with a match is refused inline.
    await edit.getByLabel('Monthly payment').fill('150.00')
    await edit.getByLabel('Auto paydown each month').check()
    await edit.getByRole('button', { name: 'Save changes' }).click()
    await expect(edit.getByRole('alert')).toContainText('not both')
    expect(await manualByName(request, name)).toMatchObject({ payment_match: 'ACME PAYLATER', payment_match_since: '2026-03-01' })

    const overview = await (await request.get('/api/accounts/overview')).json()
    const account = overview.groups.flatMap((g: { accounts: Record<string, unknown>[] }) => g.accounts).find((a: Record<string, unknown>) => a.name === name)
    expect(account).toMatchObject({ payment_match: 'ACME PAYLATER', payment_match_since: '2026-03-01', payments_applied: 0, last_payment: null })
  } finally {
    const created = await manualByName(request, name)
    if (created) await request.delete(`/api/manual/${created.id}`)
  }
})
