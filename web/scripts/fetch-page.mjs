// Fetch page innerText through headless system Chrome, for hosts that
// TLS-fingerprint-block plain HTTP clients (war.gov/defense.gov contract
// announcements — curl/urllib get Akamai 403s, a real Chrome does not).
// Usage: node scripts/fetch-page.mjs <url> [<url>...]  → JSON {url: text|null}
import { chromium } from 'playwright-core'

const urls = process.argv.slice(2)
if (!urls.length) {
  console.error('usage: node fetch-page.mjs <url> [...]')
  process.exit(1)
}

const browser = await chromium.launch({ channel: 'chrome', headless: true })
const ctx = await browser.newContext({
  userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
})
const page = await ctx.newPage()
const out = {}
for (const url of urls) {
  try {
    const resp = await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 45000 })
    if (!resp || resp.status() !== 200) {
      out[url] = null
      continue
    }
    out[url] = await page.evaluate(() => {
      const el = document.querySelector('div.body, article, main') || document.body
      return el.innerText
    })
    await page.waitForTimeout(1000)
  } catch {
    out[url] = null
  }
}
await browser.close()
process.stdout.write(JSON.stringify(out))
