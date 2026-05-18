# Web Providers

Synarch treats web access as a provider-backed tool layer. Agents request stable tools such as
`web.fetch` or `web.extract`; the gateway chooses the configured provider and enforces service,
permission, credential, event, and audit gates.

## Provider Tiers

| Tier | Providers | Key Required | Synarch Use |
| --- | --- | --- | --- |
| Basic HTTP | `local_fetch` | No | Cheap public HTML retrieval, no JavaScript. Implemented for `web.fetch` and `web.extract`. |
| Local browser | Playwright | No | JavaScript pages and browser-rendered extraction. Implemented as `local_playwright`. |
| Cloud browser | Browserbase, Browserless | Yes | Server-side browser sessions with Playwright/Puppeteer compatibility. Planned. |
| Extraction API | Firecrawl, Crawl4AI | Firecrawl yes, Crawl4AI no | Markdown/LLM-ready extraction. Firecrawl is implemented for `web.extract`; Crawl4AI is planned as local extraction. |
| Unblocking API | Browserless, Bright Data | Yes | CAPTCHA, proxy, stealth, and anti-bot-heavy flows. Planned only behind explicit human-approved provider config. |
| Scraping API | Apify, Zyte, ScrapingBee | Yes | Higher-volume scraping, proxies, marketplace actors, hosted extraction. Planned only behind explicit provider config. |

## Current Implementation

- `GET /web/providers` returns the provider catalog, implemented status, key requirement, configured
  status, risk level, and whether human approval is required before use.
- Local development needs the Python `playwright` package and Chromium browser bundle. Docker installs
  Chromium automatically for the gateway image; outside Docker run `python -m playwright install chromium`
  after installing `packages/gateway`.
- `web.extract` supports:
  - `local_fetch`: no key, uses the existing public-HTTP fetch path and returns normalized markdown-like text.
  - `local_playwright`: no key, launches local Chromium through Playwright and extracts browser-rendered HTML text.
  - `firecrawl`: requires `FIRECRAWL_API_KEY`, calls Firecrawl `/v2/scrape`, and returns markdown.
- Service registry defaults include:
  - `connector-web-local` with `web_provider=local_fetch`
  - `connector-web-browser-local` with `web_provider=local_playwright`
  - `connector-firecrawl` with `web_provider=firecrawl` and `credential_scopes=["firecrawl:api_key"]`
  - `connector-supplier-web` with `web.extract` and `web_provider=local_fetch`
- Provider candidates are visible before implementation so the UI can offer clear choices:
  Browserbase, Browserless, Bright Data, Apify, Zyte, ScrapingBee, and Crawl4AI.

## Safety Rule

Synarch should not hide CAPTCHA or bot-check bypass inside the default local provider. When a browser
or scraper hits CAPTCHA, login, 2FA, or a robots block, the correct task status is `blocked` or
`needs_review` with URL, screenshot/error, provider, and trace ID. A human can then approve a
different connector, provide credentials, choose an official API, or explicitly enable a paid
unblocking provider.

`local_playwright` marks obvious CAPTCHA, human-verification, authentication, 401/403, and 429 pages
as `ToolResult.status=blocked`. The tool output includes `blocked_reason`, `block_signals`,
`requires_human_review=true`, provider metadata, bounded `review_evidence`, and the same trace ID
carried by the tool gate. `review_evidence` is also copied into the `tool.failed` event and
`tool.blocked` audit log so reviewers can inspect the final URL, HTTP status, title, block signals,
text excerpt, and HTML excerpt without rerunning the browser. Its size is capped by
`WEB_EXTRACT_REVIEW_EVIDENCE_MAX_BYTES`.

## Provider Selection

- Use `local_fetch` first for cheap public pages without JavaScript.
- Use `local_playwright` when JavaScript rendering is required and no provider key should be needed.
- Use `firecrawl` when the expected output is clean markdown/JSON extraction and API spend is acceptable.
- Add Browserbase or Browserless next for long-running cloud browser sessions, recording, debugging, and
  agentic browser control.
- Add Browserless CAPTCHA solving or Bright Data Web Unlocker/Browser API only as an explicit
  high-risk/high-cost connector, not as an automatic fallback.

## Sources

- Playwright browser automation: https://playwright.dev/docs/intro
- Browserbase Playwright integration: https://docs.browserbase.com/introduction/playwright
- Browserless browser automation docs: https://docs.browserless.io/
- Browserless CAPTCHA solving docs: https://docs.browserless.io/baas/bot-detection/captchas
- Firecrawl scrape API: https://docs.firecrawl.dev/api-reference/endpoint/scrape
- Bright Data Web Unlocker docs: https://docs.brightdata.com/scraping-automation/web-unlocker/introduction
- Bright Data Browser API docs: https://docs.brightdata.com/scraping-automation/scraping-browser
- Crawl4AI docs: https://docs.crawl4ai.com/
- Apify docs: https://docs.apify.com/
- Zyte API docs: https://docs.zyte.com/zyte-api/
- ScrapingBee docs: https://www.scrapingbee.com/documentation/
