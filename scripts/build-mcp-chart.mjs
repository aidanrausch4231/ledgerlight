// Run from web/ after the frozen pnpm install. No runtime CDN or Node sidecar.
import { createRequire } from 'node:module'
import { mkdir, writeFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { pathToFileURL } from 'node:url'
const require = createRequire(resolve('package.json'))
const { build } = await import(pathToFileURL(require.resolve('vite')).href)
const result = await build({
  configFile: false,
  build: {
    write: false, minify: true,
    lib: { entry: resolve('src/mcp/chart.js'), name: 'LedgerlightChart', formats: ['iife'] },
    // Keep third-party @license/@preserve and /*! comments; see THIRD_PARTY_NOTICES.md.
    rolldownOptions: { output: { comments: { legal: true, annotation: false, jsdoc: false } } },
  },
})
const chunks = (Array.isArray(result) ? result : [result]).flatMap(build => build.output).filter(item => item.type === 'chunk')
if (chunks.length !== 1) throw new Error('MCP chart must be one inline bundle')
// Escape closing tags and URL slashes in JS string constants (e.g. SVG namespaces).
// These are not network permissions: CSP and the input whitelist deny all network.
const script = chunks[0].code.replace(/<\/script/gi, '<\\/script')
  .replace(/https?:\/\//g, value => value.replaceAll('/', '\\/'))
const html = `<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline' 'unsafe-eval'; style-src 'unsafe-inline'; img-src data:; connect-src 'none'; font-src 'none'; frame-src 'none'; form-action 'none'; base-uri 'none'">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ledgerlight chart</title><style>body{font:16px system-ui;margin:16px;color:#17343e;background:#fff}#chart{overflow:auto}h1{font-size:1.2rem}</style></head>
<body><h1 id="title">ledgerlight chart</h1><p id="status" role="status">Waiting for chart…</p><div id="chart" aria-label="Chart"></div><script>${script}</script></body></html>
`
const directory = resolve('../src/ledgerlight/resources')
await mkdir(directory, { recursive: true })
await writeFile(resolve(directory, 'chart.html'), html)
