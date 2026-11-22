# Tester guide

Use SEO worker only on a site you own or have clear permission to crawl. Keep the default robots.txt check enabled. Start with a low page limit and a delay of at least one second.

## Install and run

Install Python 3.9 or newer, then create an isolated environment and install the project:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
```

Copy `site.yml` to a new YAML file for your site. Change `site.name`, `site.url`, `crawl.max_pages`, `crawl.delay_seconds`, `crawl.timeout_seconds`, `crawl.user_agent` and `crawl.database`. Keep `respect_robots: true`. You can add `programmatic_templates` with a name and path regex for page families you want checked. Do not put API keys in the YAML file.

Run a single audit and open the report:

```sh
seo-worker --config my-site.yml --output reports/my-site
```

The output directory contains `report.md`, `report.html` and `report.json`. SQLite history is stored at the path configured under `crawl.database`. To include a local site repository in suggestions, add `--repo /path/to/your/repository`. `--apply` currently reports patch-ready suggestions and does not change source files. For scheduled use, run the one-shot command from cron or launchd. `--daemon` repeats at the configured interval.

Optional integrations use `GSC_ACCESS_TOKEN`, `GSC_SITE_PROPERTY`, `AHREFS_API_KEY` and `PAGESPEED_API_KEY`. Leave them unset for a crawl without API calls. Never include credentials in feedback or shared reports.

## What to verify

- The worker stays on the configured host, observes robots.txt and respects your chosen page limit and delay.
- Sitemap XML, manifest JSON, other non-HTML responses and Cloudflare email-protection URLs do not appear as audited pages.
- Findings link to the expected URLs and match what you see on those pages.
- The Markdown, HTML and JSON reports describe the same run, and a second run appears in SQLite history.
- The run works without optional API credentials and reports integrations as skipped.
- If you try an optional integration, confirm it uses the expected property/domain and check the provider's quota or billing page.

## Leave feedback

For a bug or unclear result, copy `FEEDBACK.md`, fill it in, and add the completed file to the shared folder. Comment directly on the relevant shared file too, naming the section or report finding so it is easy to locate. Do not include passwords, API keys, private page content or personal data. Attach a small sanitized report excerpt if it helps reproduce the issue.

Include the command you ran, Python version, config values with secrets removed, and whether the issue happens on another run. Mark severity as Critical, High, Medium or Low.
