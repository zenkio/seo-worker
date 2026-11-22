# SEO worker

SEO worker is a small Python crawler for repeatable technical SEO checks. It writes local Markdown, HTML and JSON reports and keeps run history in SQLite. It is for site owners and developers who want a practical crawl they can inspect, rerun and compare. It does not publish changes to a site.

The checks cover HTTP responses and redirects, titles and descriptions, canonicals, robots directives, headings, JSON-LD syntax, internal links, orphan pages, server-rendered text and configured page templates. The crawler follows same-host links, reads sitemap locations named in robots.txt, respects robots.txt by default and accepts a request delay and page limit.

## Quick start

Use Python 3.9 or newer.

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
seo-worker --config sites/demo.yml --output reports/latest
```

Open `reports/latest/report.md` for the summary, `report.html` for a browser view, and `report.json` for the full data. The sample `sites/demo.yml` targets Books to Scrape, a public demo site. For any real site, use only a site you own or have permission to crawl and create a separate YAML config for it. Set `site.url`, `site.name`, the crawl limits, a descriptive `user_agent`, a local SQLite `database` path, and any `programmatic_templates` you want checked. Keep credentials out of YAML.

## Running it

Each command runs one crawl by default. Schedule that command with cron or launchd for periodic reports. To keep the process running, use `--daemon`; it repeats at `schedule.interval_seconds` from the config, with a minimum interval of one minute. Each run replaces the selected report directory and adds a row to the SQLite history database.

```sh
# One run with a site-specific config
seo-worker --config sites/hoandduck/site.yml --output reports/hoandduck

# Include a local source repository in patch suggestions
seo-worker --config sites/demo.yml --output reports/latest --repo /path/to/site-repo

# Enable the guarded local apply workflow
seo-worker --config sites/demo.yml --output reports/latest --repo /path/to/site-repo --apply

# Repeat at the configured interval
seo-worker --config sites/demo.yml --output reports/latest --daemon
```

`--repo` points to a local website repository. It adds repository context to suggestions. With `--apply`, the worker adds a missing canonical tag to exact-match static HTML files inside that repository when it can map a crawled URL safely. Review the working tree diff before keeping those local edits. It never deploys or changes a live site.

Optional integrations read credentials from environment variables:

- `GSC_ACCESS_TOKEN` is a Google Search Console OAuth access token with read-only Search Analytics scope. `GSC_SITE_PROPERTY` can override the configured site URL with the verified property URI.
- `AHREFS_API_KEY` enables an Ahrefs Site Explorer metrics request.
- `PAGESPEED_API_KEY` enables one PageSpeed Insights request for the first crawled URL.

Without credentials, these integrations are skipped. API availability and account entitlements can affect results. The worker does not write keys to reports, but keys in shell history, process environments, or copied config files can still leak. Integrations may incur API charges under the relevant account.

## How it works

The command-line entry point in `seo_worker/cli.py` loads YAML and starts one run or a repeating loop. `seo_worker/core.py` handles robots.txt, same-host URL discovery, HTTP requests, HTML parsing, deterministic checks, optional API requests, SQLite history and report generation. It excludes known sitemap, manifest and Cloudflare email-protection utility URLs and only queues HTML responses as pages. `seo_worker/ai.py` contains an optional text drafting interface. AI is off by default, no provider is loaded by the CLI, and callers that explicitly enable it must supply a provider and a per-run token budget.

Illyism's [seo-skills](https://github.com/Illyism/seo-skills) provided workflow ideas for a recurring SEO health check, internal links, titles, content coverage and saved history. This project does not copy its source files. `seo-skills` is MIT licensed; credit goes to Illyism.

## Limits

The crawl is bounded by `crawl.max_pages`, body size and request timeout. It does not run JavaScript, so client-rendered content may be missing. It checks only the configured host and does not estimate keyword volume, competitor performance or business impact. PageSpeed checks one representative URL. Content gap checks only the YAML templates you define. A clean report does not mean a page is indexed or will rank.

## Risks

- Crawling a site without permission can violate its terms or disrupt its service. Get permission first and keep the page limit and delay conservative.
- Even a polite crawler can trigger rate limits, automated defenses or an IP ban. Stop if the site owner or service asks you to.
- Rule-based findings can be wrong or irrelevant. Review each suggested fix against the page and its purpose before changing anything.
- Optional APIs can cost money. Monitor usage and quotas with each provider.
- API keys and OAuth tokens can leak through shell history, process environments, logs or shared files. Keep them private, use limited scopes and rotate exposed keys.
- If a calling application enables AI, generated text can contain false claims or unsuitable edits. Review it before use and enforce a small budget.
- SEO changes do not guarantee rankings, traffic or conversions.
- Crawled URLs and page content may be sensitive. Reports and SQLite history contain site data; store, share and delete them according to the site owner's privacy requirements.

## Development

```sh
python -m unittest discover -s tests -v
```

The project is MIT licensed. See [LICENSE](LICENSE).

## Machine-readable output

`report.json` starts with a stable `summary` object (`schema_version` 1): site, run id, timestamp, pages crawled, findings total, counts by severity and category, new and resolved findings since the previous run, and whether Search Console is connected. Other agents should read `summary` for daily snapshots and `issues` for detail.

## Scope rules

The worker only crawls the configured site and reports. It never submits to Search Console, directories or other sites. Fixes go through pull requests on the site's own repository, reviewed and tested before publishing. Site-specific files live under `sites/<name>/`; the engine code has no site-specific paths.
