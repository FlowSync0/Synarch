# Web Providers

Synarch treats web access as a provider-backed tool layer. Agents request stable tools such as
`web.fetch` or `web.extract`; the gateway chooses the configured provider and enforces service,
permission, credential, event, and audit gates.

## Provider Tiers

| Tier | Providers | Key Required | Synarch Use |
| --- | --- | --- | --- |
| Basic HTTP | `local_fetch` | No | Cheap public HTML retrieval, no JavaScript. Implemented for `web.fetch` and `web.extract`. |
| Local browser | Playwright | No | JavaScript pages and browser-rendered extraction. Implemented as `local_playwright`. |
| Cloud browser | Browserbase, Browserless | Yes | Server-side browser sessions with Playwright/Puppeteer compatibility. Browserless `/content` extraction is implemented. |
| Extraction API | Firecrawl, Crawl4AI | Firecrawl yes, Crawl4AI no | Markdown/LLM-ready extraction. Firecrawl is implemented for `web.extract`; Crawl4AI is planned as local extraction. |
| Unblocking API | Browserless, Bright Data | Yes | CAPTCHA, proxy, stealth, and anti-bot-heavy flows. Planned only behind explicit human-approved provider config. |
| Scraping API | Apify, Zyte, ScrapingBee | Yes | Higher-volume scraping, proxies, marketplace actors, hosted extraction. Planned only behind explicit provider config. |

## Current Implementation

- `GET /web/providers` returns the provider catalog, implemented status, key requirement, configured
  status, risk level, and whether human approval is required before use.
- Gateway `POST /connectors/{service_id}/connections` stores provider API keys in the configured
  SecretVault and writes only `secret_ref` plus a short fingerprint into state-service. The default
  local vault is `.synarch/secrets`; production should swap this behind the same contract for a
  platform secret manager.
- Local development needs the Python `playwright` package and Chromium browser bundle. Synarch pins
  Playwright in `packages/gateway/pyproject.toml` so the Python package and browser bundle stay
  reproducible. Docker installs Chromium automatically for the gateway image; outside Docker run
  `python -m playwright install chromium` after installing `packages/gateway`.
- `web.extract` supports:
  - `local_fetch`: no key, uses the existing public-HTTP fetch path and returns normalized markdown-like text.
  - `local_playwright`: no key, launches local Chromium through Playwright and extracts browser-rendered HTML text.
  - `firecrawl`: requires `FIRECRAWL_API_KEY`, calls Firecrawl `/v2/scrape`, and returns markdown.
  - `browserless`: requires `BROWSERLESS_API_KEY`, calls Browserless `/content`, and returns rendered HTML text.
- Service registry defaults include:
  - `connector-web-local` with `web_provider=local_fetch`
  - `connector-web-browser-local` with `web_provider=local_playwright`
  - `connector-firecrawl` with `web_provider=firecrawl` and `credential_scopes=["firecrawl:api_key"]`
  - `connector-browserless` with `web_provider=browserless` and `credential_scopes=["browserless:api_key"]`
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
`requires_human_review=true`, provider metadata, bounded `review_evidence`,
`provider_escalation_options`, and the same trace ID carried by the tool gate. The escalation options
show candidate providers, whether they are implemented/configured, required API key environment
variables, risk level, and whether human approval is required before use. `review_evidence` and the
escalation options are also copied into the `tool.failed` event and `tool.blocked` audit log so
reviewers can inspect the final URL, HTTP status, title, block signals, text excerpt, HTML excerpt,
and provider choices without rerunning the browser. Evidence size is capped by
`WEB_EXTRACT_REVIEW_EVIDENCE_MAX_BYTES`.

## Provider Selection

- Use `local_fetch` first for cheap public pages without JavaScript.
- Use `local_playwright` when JavaScript rendering is required and no provider key should be needed.
- Use `firecrawl` when the expected output is clean markdown/JSON extraction and API spend is acceptable.
- Use `browserless` when cloud JavaScript rendering is needed and a Browserless key is configured.
- Add Browserbase next for long-running cloud browser sessions, recording, debugging, and agentic browser
  control.
- Add Browserless CAPTCHA solving or Bright Data Web Unlocker/Browser API only as an explicit
  high-risk/high-cost connector, not as an automatic fallback.

## Sources

- Playwright browser automation: https://playwright.dev/docs/intro
- Browserbase Playwright integration: https://docs.browserbase.com/introduction/playwright
- Browserless Content API: https://docs.browserless.io/rest-apis/content
- Browserless browser automation docs: https://docs.browserless.io/
- Browserless CAPTCHA solving docs: https://docs.browserless.io/baas/bot-detection/captchas
- Firecrawl scrape API: https://docs.firecrawl.dev/api-reference/endpoint/scrape
- Bright Data Web Unlocker docs: https://docs.brightdata.com/scraping-automation/web-unlocker/introduction
- Bright Data Browser API docs: https://docs.brightdata.com/scraping-automation/scraping-browser
- Crawl4AI docs: https://docs.crawl4ai.com/
- Apify docs: https://docs.apify.com/
- Zyte API docs: https://docs.zyte.com/zyte-api/
- ScrapingBee docs: https://www.scrapingbee.com/documentation/
