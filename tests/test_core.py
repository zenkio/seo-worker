import json
import tempfile
import unittest
from pathlib import Path
from seo_worker.core import DocumentParser, Page, audit, persist, history, content_gaps, compare_previous, apply_local_fixes, discover_urls, is_page_url
from seo_worker.ai import AIWriter

class ParserTests(unittest.TestCase):
    def test_extracts_metadata_headings_links_schema_and_text(self):
        p=DocumentParser("https://example.com/a")
        p.feed('<title>Hello</title><meta name="description" content="Desc"><link rel="canonical" href="/a"><h1>Heading</h1><a href="/b">B</a><script type="application/ld+json">{"@type":"Thing"}</script><p>Body text</p>')
        self.assertEqual(p.title,"Hello")
        self.assertEqual(p.description,"Desc")
        self.assertEqual(p.canonical,"https://example.com/a")
        self.assertEqual(p.headings,[(1,"Heading")])
        self.assertEqual(p.links,["https://example.com/b"])
        self.assertEqual(json.loads(p.jsonld[0])["@type"],"Thing")
        self.assertIn("Body text",p.text)

    def test_filters_utility_urls(self):
        self.assertFalse(is_page_url("https://example.com/sitemap.xml"))
        self.assertFalse(is_page_url("https://example.com/manifest.json"))
        self.assertFalse(is_page_url("https://example.com/cdn-cgi/l/email-protection#abc"))
        self.assertTrue(is_page_url("https://example.com/guide/"))

    def test_discovery_keeps_only_html_and_skips_utility_paths(self):
        class Fetcher:
            _robots = {}
            def fetch(self, url):
                pages = {
                    "https://example.com/": Page(url, 200, url, 1, links=[
                        "https://example.com/guide/", "https://example.com/feed.xml",
                        "https://example.com/manifest.json", "https://example.com/cdn-cgi/l/email-protection#x"]),
                    "https://example.com/guide/": Page(url, 200, url, 1, content_type="text/html"),
                    "https://example.com/feed.xml": Page(url, 200, url, 1, content_type="application/xml"),
                }
                return pages[url]
        self.assertEqual(discover_urls("https://example.com/", Fetcher(), 10), [
            "https://example.com/", "https://example.com/guide/"])

class AuditTests(unittest.TestCase):
    def test_ai_writer_is_off_by_default_and_budgeted(self):
        class Provider:
            def complete(self, prompt, max_tokens): return "draft"
        self.assertIsNone(AIWriter(provider=Provider(), budget_tokens=50).draft("prompt"))
        writer=AIWriter(enabled=True, provider=Provider(), budget_tokens=8)
        self.assertEqual(writer.draft("prompt", max_tokens=8), "draft")
        self.assertIsNone(writer.draft("second", max_tokens=8))

    def test_reports_missing_fields_and_links(self):
        page=Page("https://example.com/",200,"https://example.com/",10,text="body",links=["https://example.com/missing"])
        missing=Page("https://example.com/missing",404,"https://example.com/missing",10)
        cfg={"site":{"url":"https://example.com/"}}
        categories={x["category"] for x in audit([page,missing],cfg)}
        self.assertTrue({"metadata","canonical","headings","broken_link"}.issubset(categories))

    def test_history_persists_runs(self):
        with tempfile.TemporaryDirectory() as d:
            db=Path(d)/"state.sqlite3"
            rid=persist(db,[Page("u",200,"u",1)],[{"url":"u","severity":"low","category":"x","message":"m"}])
            self.assertEqual(history(db)[0]["id"],rid)
            self.assertEqual(history(db)[0]["issues"],1)
            rid2=persist(db,[Page("u",200,"u",1,title="Updated")],[])
            comparison=compare_previous(db,rid2,[Page("u",200,"u",1,title="Updated")],[])
            self.assertEqual(comparison["issue_count_delta"],-1)
            self.assertEqual(comparison["resolved_findings"],1)
            self.assertEqual(len(comparison["changed_page_metrics"]),1)

    def test_apply_adds_canonical_only_to_exact_local_html(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); (root/"index.html").write_text("<html><head></head><body>Home</body></html>",encoding="utf-8")
            page=Page("https://example.com/",200,"https://example.com/",1)
            changes=apply_local_fixes(root,[page],"https://example.com/")
            self.assertEqual(len(changes),1)
            self.assertIn('<link rel="canonical" href="https://example.com/">',(root/"index.html").read_text())

    def test_template_gap(self):
        gaps=content_gaps({"programmatic_templates":[{"name":"docs","path_pattern":"/docs/"}]},[])
        self.assertEqual(gaps[0]["type"],"programmatic_template_gap")

if __name__ == "__main__": unittest.main()


class CanonicalMismatchTests(unittest.TestCase):
    def test_canonical_differs_from_crawled_url(self):
        pg=Page("https://e.com/about",200,"https://e.com/about",1,"T","D","https://e.com/about.html","",[(1,"H")],[],[],"text","","text/html")
        cfg={"site":{"url":"https://e.com/"}}
        msgs=[i["message"] for i in audit([pg],cfg) if i["category"]=="canonical"]
        self.assertTrue(any("differs from the crawled URL" in m for m in msgs))
