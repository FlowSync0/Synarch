# Web Providers

Synarch treats web access as a provider-backed tool layer. Agents request stable tools such as
`web.fetch` or `web.extract`; the gateway chooses the configured provider and enforces service,
permission, credential, event, and audit gates.

## Provider Tiers

| Tier | Providers | Key Required | Synarch Use |
| --- | --- | --- | --- |
| Basic HTTP | `local_fetch` | No | Cheap public HTML retrieval, no JavaScript. Implemented for `web.fetch` and `web.extract`. |
| Local browser | Playwright | No | JavaScript pages, forms, screenshots, human-assisted sessions. Planned as `local_playwright`. |
| Cloud browser | Browserbase, Browserless | Yes | Server-side browser sessions with Playwright/Puppeteer compatibility. Planned. |
| Extraction API | Firecrawl, Crawl4AI | Firecrawl yes, Crawl4AI no | Markdown/LLM-ready extraction. Firecrawl is implemented for `web.extract`; Crawl4AI is planned as local extraction. |
| Scraping API | Apify, Zyte, ScrapingBee | Yes | Higher-volume scraping, proxies, marketplace actors, hosted extraction. Planned only behind explicit provider config. |

## Current Implementation

- `GET /web/providers` returns the provider catalog, implemented status, key requirement, and whether
  the needed key is configured in the environment.
- `web.extract` supports:
  - `local_fetch`: no key, uses the existing public-HTTP fetch path and returns normalized markdown-like text.
  - `firecrawl`: requires `FIRECRAWL_API_KEY`, calls Firecrawl `/v2/scrape`, and returns markdown.
- Service registry defaults include:
  - `connector-web-local` with `web_provider=local_fetch`
  - `connector-firecrawl` with `web_provider=firecrawl` and `credential_scopes=["firecrawl:api_key"]`
  - `connector-supplier-web` with `web.extract` and `web_provider=local_fetch`

## Safety Rule

Synarch should not implement an explicit CAPTCHA or bot-check bypass tool. When a browser or scraper
hits CAPTCHA, login, 2FA, or a robots block, the correct task status is `blocked` or `needs_review`
with URL, screenshot/error, provider, and trace ID. A human can then approve a different connector,
provide credentials, or choose an official API.

## Sources

- Playwright browser automation: https://playwright.dev/docs/intro
- Browserbase Playwright integration: https://docs.browserbase.com/integrations/playwright
- Browserless browser automation docs: https://docs.browserless.io/
- Firecrawl scrape API: https://docs.firecrawl.dev/api-reference/endpoint/scrape
- Crawl4AI docs: https://docs.crawl4ai.com/
- Apify docs: https://docs.apify.com/
- Zyte API docs: https://docs.zyte.com/zyte-api/
- ScrapingBee docs: https://www.scrapingbee.com/documentation/
