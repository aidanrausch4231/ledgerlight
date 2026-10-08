import { test, expect } from '@playwright/test'

// Offline fake Plaid: "<identity>@<key>" public tokens are separate synthetic Items
// at institution <key>, with the same masks as every other synthetic Item there.
const COPY = 'public-synthetic-duplicate@public-synthetic-ledgerlight'

test('linking an already linked bank shows the duplicate message', async ({ page, request }) => {
  test.skip(process.env.LEDGERLIGHT_E2E_PLAID === 'sandbox', 'Offline fake only')
  await page.route('**/*', route => new URL(route.request().url()).hostname === '127.0.0.1' ? route.continue() : route.abort())
  expect((await request.post('/api/plaid/exchange', { data: { public_token: 'public-synthetic-ledgerlight' } })).ok()).toBeTruthy()
  const before = await (await request.get('/api/plaid/items')).json()
  // The fake Link flow always relinks the same Item; send a second Item of the
  // same bank instead so the real server duplicate check answers HTTP 409.
  let status = 0
  await page.route('**/api/plaid/exchange', async route => {
    const body = route.request().postDataJSON()
    const response = await route.fetch({ postData: JSON.stringify({ ...body, public_token: `${COPY}:${body.link_token}` }) })
    status = response.status()
    await route.fulfill({ response })
  })
  await page.goto('/#/accounts')
  await page.locator('.account-link-desktop').click()
  await expect(page.getByRole('alert')).toHaveText(
    'Synthetic Bank is already linked (Synthetic Checking ••0001, Synthetic Credit ••0002). Remove the old link first if you want to link it again.',
  )
  expect(status).toBe(409)
  await expect(page.getByText('Account linked.')).toHaveCount(0)
  expect(await (await request.get('/api/plaid/items')).json()).toHaveLength(before.length)
  expect(await (await request.get('/api/plaid/duplicates')).json()).toEqual([])
})
