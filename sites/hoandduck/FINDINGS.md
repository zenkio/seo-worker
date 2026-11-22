# Ho & Duck findings

This summary uses the supplied audit notes, paste-ready suggestions and refreshed worker run. The original crawl checked 20 URLs. After the crawler fix, the refreshed run checked 17 pages and reported seven remaining findings, all low-priority title-length flags. Both runs respected robots.txt and used a one-second delay. Search Console, Ahrefs and PageSpeed credentials were absent, and no source repository for the site was available. These findings describe the supplied snapshot, not an independent ranking check.

## Priorities

1. **Check indexing in Search Console.** The supplied audit did not find Ho & Duck in its public web searches, but that does not establish whether Google has indexed the site. Verify the domain property, inspect the homepage and three main landing pages, review query impressions and canonical/indexing status, then submit the existing sitemap if appropriate. Account access and approval from the site owner are needed for those actions.
2. **Review long titles on key pages.** The worker flagged the homepage at 75 characters and `/life-in-the-uk-practice-test/` at 71. The mock-test title was 62 characters. The supplied suggestions shorten these while retaining the page intent. Length alone is not a defect, so compare each proposal with the visible page and user wording before applying it. Several chapter titles were also flagged, with the longest at 78 characters.
3. **Keep practice routes easy to reach.** Link the practice test, timed mock and chapter hub from relevant homepage, study and question pages. Use copy that explains what a visitor will get. The current evidence confirms these pages exist, but does not prove how prominent they are in all site navigation.
4. **Keep the landing pages distinct.** The practice, mock-test and free-test pages target closely related searches. Give each a clear job: starting a practice session, taking a timed mock, or understanding free access. Avoid copying the same blocks between them.
5. **Add depth where it helps learners.** The supplied audit describes useful chapter summaries and original questions. Consider adding question-format guidance, advice on timed practice, and links from each chapter guide to relevant practice. Do not create thin pages just to target another phrase.
6. **Save a Search Console baseline.** Record page and query impressions, clicks and position before judging changes. Review monthly. The supplied audit found no critical issue on the crawled HTML landing pages, but it did not measure organic performance through Search Console.

## Locale and ranking notes

The supplied audit saw `lang="en-GB"` and a `.uk` domain. It recommends keeping examples and spelling consistent for UK users. There is no alternate locale in the evidence, so the audit did not recommend adding an `hreflang` cluster now. Treat any locale metadata changes as conditional on the site adding genuine alternate versions.

No title or technical change can promise rankings. The supplied audit describes established competition for broad Life in the UK terms and recommends measuring progress in Search Console rather than relying on a single manual search.

## Source material

This note summarizes `audit-and-fixes.md`, `ready-to-paste.md` and the refreshed machine reports under the supplied Ho & Duck evidence folder. No changes were made to the live site.
