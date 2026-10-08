import { defineConfig } from '@playwright/test'
import { createServer } from 'node:net'
import { mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

// Inherit this synthetic-only directory in CLI calls as well as the web server.
process.env.LEDGERLIGHT_E2E_STORAGE ||= mkdtempSync(join(tmpdir(), 'ledgerlight-browser-'))

const port = process.env.LEDGERLIGHT_E2E_PORT ? Number(process.env.LEDGERLIGHT_E2E_PORT) : await new Promise<number>((resolve, reject) => {
  const server = createServer()
  server.on('error', reject)
  server.listen(0, '127.0.0.1', () => {
    const address = server.address()
    if (!address || typeof address === 'string') return reject(new Error('No free port'))
    server.close(() => resolve(address.port))
  })
})
// Playwright re-evaluates config in workers; reuse the parent's allocated port.
process.env.LEDGERLIGHT_E2E_PORT = String(port)

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  reporter: 'list',
  use: {
    baseURL: `http://127.0.0.1:${port}`, browserName: 'chromium', trace: 'retain-on-failure', screenshot: 'off',
    launchOptions: { args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream'] },
  },
  webServer: {
    command: `uv run python web/e2e/serve.py ${port}`,
    cwd: '..',
    url: `http://127.0.0.1:${port}/api/health`,
    reuseExistingServer: false,
    timeout: 120000,
    gracefulShutdown: { signal: 'SIGTERM', timeout: 10000 },
  },
})
