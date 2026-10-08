#!/usr/bin/env node
// Regenerate README screenshots in docs/images/ from SYNTHETIC demo data only.
// Usage (after `cd web && pnpm install --frozen-lockfile && pnpm build`):
//   node scripts/screenshots.mjs
// Uses a throwaway LEDGERLIGHT_DATA_DIR/CONFIG_DIR, the fake LLM provider and
// fake Plaid; never reads or writes your real ledgerlight storage.
import { execFileSync, spawn } from 'node:child_process'
import { existsSync, mkdirSync, mkdtempSync, rmSync } from 'node:fs'
import { createRequire } from 'node:module'
import { createServer } from 'node:net'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const TODAY = '2026-03-15'
const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const out = join(root, 'docs', 'images')
if (!existsSync(join(root, 'web', 'dist', 'index.html'))) {
  throw new Error('Build the web UI first: cd web && pnpm install --frozen-lockfile && pnpm build')
}
const { chromium } = createRequire(join(root, 'web', 'package.json'))('@playwright/test')

const storage = mkdtempSync(join(tmpdir(), 'ledgerlight-shots-'))
const env = { ...process.env }
for (const key of ['PLAID_CLIENT_ID', 'PLAID_SECRET', 'OPENAI_API_KEY', 'ANTHROPIC_API_KEY',
  'OLLAMA_HOST', 'OLLAMA_MODEL', 'LEDGERLIGHT_E2E_PLAID']) delete env[key]
Object.assign(env, {
  LEDGERLIGHT_DATA_DIR: join(storage, 'data'),
  LEDGERLIGHT_CONFIG_DIR: join(storage, 'config'),
  LEDGERLIGHT_TODAY: TODAY, // fixed date keeps screenshots reproducible
  LEDGERLIGHT_LLM_PROVIDER: 'fake',
  LEDGERLIGHT_FAKE_PLAID: '1',
  LEDGERLIGHT_FAKE_PRICES: '1',
  PLAID_ENV: 'sandbox',
})
const cli = (...args) => execFileSync('uv', ['run', 'ledgerlight', '--json', ...args], { cwd: root, env, stdio: ['ignore', 'ignore', 'inherit'] })

// Synthetic fixtures: demo seed plus a few demo-named budgets, a goal and manual accounts.
cli('demo', 'seed')
for (const [category, limit] of [['Food & Drink', '180'], ['Groceries', '400'], ['Transport', '120'], ['Entertainment', '15']]) {
  cli('budgets', 'set', category, limit)
}
cli('goals', 'add', '--name', 'Demo Rainy Day Fund', '--target-amount', '8000', '--account', 'demo-savings', '--target-date', '2026-12-31')
cli('manual', 'add', '--kind', 'cash', '--name', 'Demo Cash Envelope', '--balance', '300')

const port = await new Promise((resolve, reject) => {
  const server = createServer().on('error', reject)
  server.listen(0, '127.0.0.1', () => { const { port } = server.address(); server.close(() => resolve(port)) })
})
const serve = spawn('uv', ['run', 'ledgerlight', 'serve', '--port', String(port)], { cwd: root, env, stdio: ['ignore', 'ignore', 'inherit'] })
const base = `http://127.0.0.1:${port}`
for (let i = 0; ; i++) {
  try { if ((await fetch(`${base}/api/health`)).ok) break } catch { /* not up yet */ }
  if (i > 120) throw new Error('server did not start')
  await new Promise(r => setTimeout(r, 500))
}

mkdirSync(out, { recursive: true })
const browser = await chromium.launch()
try {
  const open = async (theme, hash) => {
    const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, colorScheme: theme })
    await context.clock.setFixedTime(new Date(`${TODAY}T10:00:00`)) // match the server's date
    await context.addInitScript(t => localStorage.setItem('ledgerlight-theme', t), theme)
    const page = await context.newPage()
    await page.goto(`${base}/#${hash}`)
    await page.getByText('Live UI connected').waitFor()
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(800) // let charts and motion settle
    return page
  }
  const shoot = async (page, name) => {
    await page.screenshot({ path: join(out, name) })
    console.log(join('docs', 'images', name))
    await page.context().close()
  }
  await shoot(await open('light', '/'), 'home.png')
  await shoot(await open('dark', '/'), 'home-dark.png')
  // Added after the Home shots: a loan added "today" has no balance history,
  // so it would show as a one-day net-worth cliff on the Home chart.
  cli('manual', 'add', '--kind', 'auto_loan', '--name', 'Demo Car Loan', '--balance', '6400', '--apr', '4.9', '--payment', '250', '--payment-day', '5')
  await shoot(await open('light', '/accounts'), 'accounts.png')
  await shoot(await open('light', '/budgets'), 'budgets.png')

  const ask = await open('light', '/')
  await ask.getByRole('button', { name: 'Chat', exact: true }).click()
  const message = ask.getByRole('textbox', { name: 'Message', exact: true })
  await message.fill('hey what was my coffee spend like')
  await message.press('Enter')
  const panel = ask.getByRole('region', { name: 'Answer', exact: true })
  await panel.locator('.chart svg').nth(1).waitFor()
  await ask.getByRole('button', { name: 'Send', exact: true }).waitFor()
  await ask.waitForTimeout(800)
  await shoot(ask, 'ask.png')
} finally {
  await browser.close()
  serve.kill('SIGTERM')
  await new Promise(r => serve.once('exit', r))
  rmSync(storage, { recursive: true, force: true })
}
