from __future__ import annotations

import json
import os
import html
import re
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.robotparser
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict, deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple


@dataclass
class Page:
    url: str
    status: int
    final_url: str
    elapsed_ms: int
    title: str = ""
    description: str = ""
    canonical: str = ""
    robots: str = ""
    headings: List[Tuple[int, str]] = field(default_factory=list)
    links: List[str] = field(default_factory=list)
    jsonld: List[str] = field(default_factory=list)
    text: str = ""
    error: str = ""
    content_type: str = ""


class DocumentParser(HTMLParser):
    def __init__(self, base_url: str):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.title = ""
        self.description = ""
        self.canonical = ""
        self.robots = ""
        self.headings: List[Tuple[int, str]] = []
        self.links: List[str] = []
        self.jsonld: List[str] = []
        self._title = False
        self._heading: Optional[int] = None
        self._heading_text = ""
        self._script = False
        self._script_type = ""
        self._script_text = ""
        self._skip_depth = 0
        self._text: List[str] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        a = dict(attrs)
        if tag in ("script", "style", "noscript", "svg"):
            self._skip_depth += 1
        if tag == "title": self._title = True
        if re.fullmatch(r"h[1-6]", tag):
            self._heading = int(tag[1]); self._heading_text = ""
        if tag == "meta":
            name = (a.get("name") or "").lower()
            if name == "description": self.description = a.get("content", "").strip()
            if name == "robots": self.robots = a.get("content", "").strip()
        if tag == "link" and "canonical" in (a.get("rel") or "").lower().split():
            self.canonical = urllib.parse.urljoin(self.base_url, a.get("href", ""))
        if tag == "a" and a.get("href"):
            self.links.append(urllib.parse.urljoin(self.base_url, a["href"].strip()))
        if tag == "script":
            self._script = True; self._script_type = a.get("type", "").lower(); self._script_text = ""

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style", "noscript", "svg") and self._skip_depth:
            self._skip_depth -= 1
        if tag == "title": self._title = False
        if re.fullmatch(r"h[1-6]", tag) and self._heading is not None:
            self.headings.append((self._heading, " ".join(self._heading_text.split())))
            self._heading = None
        if tag == "script":
            if self._script_type == "application/ld+json" and self._script_text.strip(): self.jsonld.append(self._script_text.strip())
            self._script = False

    def handle_data(self, data: str) -> None:
        if self._title: self.title += data
        if self._heading is not None: self._heading_text += data
        if self._script: self._script_text += data
        if not self._skip_depth and data.strip(): self._text.append(data.strip())

    @property
    def text(self) -> str:
        return " ".join(self._text)


class PoliteFetcher:
    def __init__(self, user_agent: str, delay: float, timeout: float, respect_robots: bool = True):
        self.user_agent = user_agent
        self.delay = delay
        self.timeout = timeout
        self.respect_robots = respect_robots
        self._last = 0.0
        self._robots: Dict[str, urllib.robotparser.RobotFileParser] = {}

    def allowed(self, url: str) -> bool:
        if not self.respect_robots: return True
        parts = urllib.parse.urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self._robots:
            parser = urllib.robotparser.RobotFileParser(origin + "/robots.txt")
            try:
                req = urllib.request.Request(origin + "/robots.txt", headers={"User-Agent": self.user_agent})
                with urllib.request.urlopen(req, timeout=self.timeout) as r: parser.parse(r.read(512_000).decode("utf-8", "replace").splitlines())
            except Exception:
                parser.parse([])
            self._robots[origin] = parser
        return self._robots[origin].can_fetch(self.user_agent, url)

    def fetch(self, url: str) -> Page:
        if not self.allowed(url): return Page(url, 0, url, 0, error="blocked by robots.txt")
        wait = self.delay - (time.monotonic() - self._last)
        if wait > 0: time.sleep(wait)
        started = time.monotonic(); status = 0; final = url; body = b""; error = ""; content_type = ""
        try:
            req = urllib.request.Request(url, headers={"User-Agent": self.user_agent, "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"})
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                status = response.status; final = response.geturl(); content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower(); body = response.read(2_000_000)
        except urllib.error.HTTPError as exc:
            status = exc.code; final = exc.geturl()
            try: body = exc.read(2_000_000); content_type = exc.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
            except Exception: pass
            error = str(exc)
        except Exception as exc: error = str(exc)
        self._last = time.monotonic()
        p = DocumentParser(final)
        if not content_type or content_type in ("text/html", "application/xhtml+xml"):
            try: p.feed(body.decode("utf-8", "replace"))
            except Exception as exc: error = error or str(exc)
        return Page(url, status, final, int((time.monotonic()-started)*1000), p.title.strip(), p.description, p.canonical, p.robots, p.headings, p.links, p.jsonld, p.text[:10000], error, content_type)


def read_config(path: Path) -> dict:
    import yaml
    with path.open(encoding="utf-8") as f: data = yaml.safe_load(f) or {}
    if not data.get("site", {}).get("url"): raise ValueError("config needs site.url")
    data.setdefault("crawl", {})
    data["crawl"].setdefault("max_pages", 100)
    data["crawl"].setdefault("delay_seconds", 1.0)
    data["crawl"].setdefault("timeout_seconds", 15)
    return data


def same_site(a: str, b: str) -> bool:
    return urllib.parse.urlsplit(a).netloc.lower() == urllib.parse.urlsplit(b).netloc.lower()


def is_page_url(url: str) -> bool:
    path = urllib.parse.urlsplit(url).path.lower()
    if path in ("/sitemap.xml", "/manifest.json"):
        return False
    return not path.startswith("/cdn-cgi/l/email-protection")


def discover_urls(base: str, fetcher: PoliteFetcher, max_pages: int) -> List[str]:
    queue = deque([base]); seen: Set[str] = set(); found: List[str] = []
    origin = urllib.parse.urlsplit(base)
    # robots was already fetched by fetcher; read sitemap directives if available.
    parser = fetcher._robots.get(f"{origin.scheme}://{origin.netloc}")
    if parser:
        for sm in parser.site_maps() or []:
            try:
                req = urllib.request.Request(sm, headers={"User-Agent": fetcher.user_agent})
                with urllib.request.urlopen(req, timeout=fetcher.timeout) as response: root = ET.fromstring(response.read(2_000_000))
                for node in root.iter():
                    if node.tag.endswith("loc") and node.text and same_site(node.text.strip(), base): queue.append(node.text.strip())
            except Exception: pass
    while queue and len(found) < max_pages:
        url = queue.popleft()
        url = urllib.parse.urldefrag(url)[0]
        if url in seen or not same_site(url, base) or not is_page_url(url): continue
        seen.add(url)
        page = fetcher.fetch(url)
        if page.content_type and page.content_type not in ("text/html", "application/xhtml+xml"):
            continue
        found.append(url)
        if page.status and page.status < 400:
            for link in page.links:
                clean = urllib.parse.urldefrag(link)[0]
                parts = urllib.parse.urlsplit(clean)
                if parts.scheme in ("http", "https") and same_site(clean, base) and clean not in seen: queue.append(clean)
    return found


def audit(pages: List[Page], cfg: dict) -> List[dict]:
    issues: List[dict] = []
    def add(page: Page, severity: str, category: str, message: str, suggestion: str = ""):
        issues.append({"url": page.url, "severity": severity, "category": category, "message": message, "suggestion": suggestion})
    titles = Counter(p.title.strip().lower() for p in pages if p.title.strip())
    descs = Counter(p.description.strip().lower() for p in pages if p.description.strip())
    page_by_url = {p.url: p for p in pages}
    urlset = set(page_by_url)
    inbound = Counter()
    for p in pages:
        for link in p.links:
            if link in urlset: inbound[link] += 1
    for p in pages:
        if not p.status or p.status >= 400: add(p, "critical", "http", f"Page returned HTTP {p.status or 'error'}{': ' + p.error if p.error else ''}", "Check the route or server response."); continue
        if p.final_url != p.url and p.final_url != p.url.rstrip("/"): add(p, "high", "redirect", f"Redirected to {p.final_url}", "Update internal links to the final URL and verify the redirect target.")
        if not p.title: add(p,"high","metadata","Missing title","Add a unique, descriptive title in the page template.")
        elif len(p.title)>60: add(p,"low","metadata",f"Title is {len(p.title)} characters","Review for clarity and likely search result truncation.")
        elif titles[p.title.lower()]>1: add(p,"high","metadata","Duplicate title","Make the title specific to this page.")
        if not p.description: add(p,"medium","metadata","Missing meta description","Write a concise summary of this page.")
        elif descs[p.description.lower()]>1: add(p,"medium","metadata","Duplicate meta description","Write a page-specific description.")
        if not p.canonical: add(p,"medium","canonical","Missing canonical URL","Add an absolute canonical URL for the preferred page.")
        elif not same_site(p.canonical,p.url): add(p,"high","canonical",f"Canonical points off-site: {p.canonical}","Check whether cross-domain canonicalization is intentional.")
        elif p.canonical.rstrip("/")!=p.final_url.rstrip("/"): add(p,"medium","canonical",f"Canonical {p.canonical} differs from the crawled URL {p.final_url}","Make internal links, the sitemap and the canonical use one URL form for this page.")
        if "noindex" in p.robots.lower(): add(p,"high","indexing","Page has noindex directive","Confirm this page should be excluded from search.")
        h1=[h for n,h in p.headings if n==1]
        if len(h1)!=1: add(p,"medium","headings",f"Page has {len(h1)} H1 headings","Use one clear H1 that describes the main topic.")
        try:
            for raw in p.jsonld: json.loads(raw)
        except Exception: add(p,"medium","structured_data","Invalid JSON-LD","Validate the JSON-LD script syntax.")
        for link in p.links:
            target = page_by_url.get(link)
            if target and (not target.status or target.status >= 400):
                add(p,"high","broken_link",f"Internal link returns HTTP {target.status or 'error'}: {link}","Update or remove the link.")
        if inbound[p.url]==0 and p.url.rstrip("/") not in (cfg["site"]["url"].rstrip("/"),): add(p,"low","internal_link","Page has no inbound internal links","Link to this page from a relevant, crawlable page.")
        if not p.text: add(p,"high","content","No readable server-rendered text found","Check server rendering and crawler access.")
    return issues


def optional_integrations(cfg: dict, urls: List[str]) -> dict:
    import os
    from datetime import date, timedelta
    result = {"integrations": {"google_search_console": "skipped: set GSC_ACCESS_TOKEN", "ahrefs": "skipped: set AHREFS_API_KEY", "pagespeed": "skipped: set PAGESPEED_API_KEY"}}
    site_url=cfg["site"]["url"]
    gsc_token=os.getenv("GSC_ACCESS_TOKEN")
    if gsc_token:
        property_url=os.getenv("GSC_SITE_PROPERTY",site_url)
        # Search Console data can lag; query the latest 28 complete days.
        end=date.today()-timedelta(days=3); start=end-timedelta(days=27)
        endpoint="https://www.googleapis.com/webmasters/v3/sites/"+urllib.parse.quote(property_url,safe="")+"/searchAnalytics/query"
        body=json.dumps({"startDate":start.isoformat(),"endDate":end.isoformat(),"dimensions":["page"],"rowLimit":250,"type":"web"}).encode()
        try:
            req=urllib.request.Request(endpoint,data=body,headers={"Authorization":"Bearer "+gsc_token,"Content-Type":"application/json","Accept":"application/json"},method="POST")
            with urllib.request.urlopen(req,timeout=30) as response: result["google_search_console"]=json.load(response)
            result["integrations"]["google_search_console"]="measured"
        except Exception: result["integrations"]["google_search_console"]="error: request failed; check OAuth access, property, and quota"
    ahrefs_key=os.getenv("AHREFS_API_KEY")
    if ahrefs_key:
        parsed=urllib.parse.urlsplit(site_url)
        target=parsed.netloc
        query=urllib.parse.urlencode({"target":target,"date":date.today().isoformat(),"mode":"domain","protocol":"both"})
        endpoint="https://api.ahrefs.com/v3/site-explorer/metrics?"+query
        try:
            req=urllib.request.Request(endpoint,headers={"Authorization":"Bearer "+ahrefs_key,"Accept":"application/json"})
            with urllib.request.urlopen(req,timeout=30) as response: result["ahrefs"]=json.load(response)
            result["integrations"]["ahrefs"]="measured"
        except Exception: result["integrations"]["ahrefs"]="error: request failed; check API access, target, and units"
    psi_key=os.getenv("PAGESPEED_API_KEY")
    if psi_key:
        target=urllib.parse.quote(urls[0], safe="") if urls else ""
        if target:
            endpoint=f"https://www.googleapis.com/pagespeedonline/v5/runPagespeed?url={target}&key={urllib.parse.quote(psi_key)}&category=performance"
            try:
                req=urllib.request.Request(endpoint,headers={"User-Agent":"seo-worker/0.1"})
                with urllib.request.urlopen(req,timeout=30) as response: data=json.load(response)
                audits=data.get("lighthouseResult",{}).get("audits",{})
                result["pagespeed"]={k: audits.get(k,{}).get("displayValue") for k in ("largest-contentful-paint","cumulative-layout-shift","interaction-to-next-paint")}
                result["integrations"]["pagespeed"]="measured"
            except Exception: result["integrations"]["pagespeed"]="error: request failed; check API key and quota"
    return result


def persist(db_path: Path, pages: List[Page], issues: List[dict]) -> int:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con=sqlite3.connect(db_path)
    con.executescript("CREATE TABLE IF NOT EXISTS runs(id INTEGER PRIMARY KEY, started_at TEXT NOT NULL, page_count INTEGER NOT NULL, issue_count INTEGER NOT NULL); CREATE TABLE IF NOT EXISTS pages(run_id INTEGER, url TEXT, status INTEGER, title TEXT, description TEXT, elapsed_ms INTEGER, PRIMARY KEY(run_id,url)); CREATE TABLE IF NOT EXISTS issues(run_id INTEGER, url TEXT, severity TEXT, category TEXT, message TEXT);")
    now=datetime.now(timezone.utc).isoformat()
    cur=con.execute("INSERT INTO runs(started_at,page_count,issue_count) VALUES(?,?,?)",(now,len(pages),len(issues))); rid=cur.lastrowid
    con.executemany("INSERT INTO pages VALUES(?,?,?,?,?,?)",[(rid,p.url,p.status,p.title,p.description,p.elapsed_ms) for p in pages])
    con.executemany("INSERT INTO issues VALUES(?,?,?,?,?)",[(rid,i["url"],i["severity"],i["category"],i["message"]) for i in issues])
    con.commit(); con.close(); return rid


def history(db_path: Path) -> list:
    if not db_path.exists(): return []
    con=sqlite3.connect(db_path); rows=con.execute("SELECT id,started_at,page_count,issue_count FROM runs ORDER BY id DESC LIMIT 10").fetchall(); con.close()
    return [{"id":r[0],"started_at":r[1],"pages":r[2],"issues":r[3]} for r in rows]

def compare_previous(db_path: Path, run_id: int, pages: List[Page], issues: List[dict]) -> dict:
    if not db_path.exists(): return {"available":False}
    con=sqlite3.connect(db_path)
    previous=con.execute("SELECT id,page_count,issue_count FROM runs WHERE id < ? ORDER BY id DESC LIMIT 1",(run_id,)).fetchone()
    if not previous:
        con.close(); return {"available":False}
    prior_id,prior_pages,prior_issues=previous
    prior_rows=con.execute("SELECT url,status,title,description FROM pages WHERE run_id=?",(prior_id,)).fetchall()
    prior_page_map={r[0]:r[1:] for r in prior_rows}
    prior_issue_set={(r[0],r[1],r[2]) for r in con.execute("SELECT url,category,message FROM issues WHERE run_id=?",(prior_id,)).fetchall()}
    con.close()
    current_issue_set={(i["url"],i["category"],i["message"]) for i in issues}
    changed=[]
    for page in pages:
        old=prior_page_map.get(page.url)
        if old and tuple(old)!=(page.status,page.title,page.description):
            changed.append({"url":page.url,"before":{"status":old[0],"title":old[1],"description":old[2]},"after":{"status":page.status,"title":page.title,"description":page.description}})
    return {"available":True,"previous_run_id":prior_id,"page_count_delta":len(pages)-prior_pages,"issue_count_delta":len(issues)-prior_issues,"resolved_findings":len(prior_issue_set-current_issue_set),"new_findings":len(current_issue_set-prior_issue_set),"changed_page_metrics":changed}


def suggestions(pages: List[Page], repo: Optional[Path]) -> list:
    result=[]
    if repo:
        result.append({"type":"repo_review","path":str(repo),"message":"Use the audit URLs and categories to locate the owning templates; no files were changed."})
    for p in pages:
        if not p.title: result.append({"type":"patch_suggestion","url":p.url,"suggestion":"Add a unique <title> in the page template."})
    return result


def apply_local_fixes(repo: Path, pages: List[Page], base_url: str) -> list:
    """Add missing canonical tags only to exact-match static HTML files in a local repo."""
    import os
    root=repo.resolve()
    applied=[]
    for page in pages:
        if not page.status or page.status >= 400 or page.canonical: continue
        parts=urllib.parse.urlsplit(page.url)
        if parts.netloc.lower()!=urllib.parse.urlsplit(base_url).netloc.lower(): continue
        relative=parts.path.lstrip("/")
        candidates=[root/(relative or "index.html")]
        if not relative or parts.path.endswith("/"): candidates.append(root/relative/"index.html")
        target=next((candidate.resolve() for candidate in candidates if candidate.exists() and candidate.is_file() and candidate.suffix.lower()==".html"),None)
        if target is None or root not in target.parents and target!=root: continue
        try: source=target.read_text(encoding="utf-8")
        except (OSError,UnicodeError): continue
        if re.search(r"<link\b[^>]*\brel\s*=\s*['\"]?canonical\b",source,re.I): continue
        tag=f'<link rel="canonical" href="{html.escape(page.url,quote=True)}">'
        updated,count=re.subn(r"<head(?:\s[^>]*)?>",lambda m:m.group(0)+"\n  "+tag,source,count=1,flags=re.I)
        if count:
            target.write_text(updated,encoding="utf-8")
            applied.append({"path":str(target),"change":"added missing canonical link","url":page.url})
    return applied


def content_gaps(cfg: dict, pages: List[Page]) -> list:
    templates=cfg.get("programmatic_templates",[])
    out=[]
    for t in templates:
        pattern=t.get("path_pattern","")
        matching=[p.url for p in pages if pattern and re.search(pattern,urllib.parse.urlsplit(p.url).path)]
        if not matching: out.append({"type":"programmatic_template_gap","pattern":pattern,"message":f"No crawled pages match template '{t.get('name',pattern)}'."})
    return out


def run(config_path: Path, output_dir: Path, repo: Optional[Path]=None, apply: bool=False) -> dict:
    cfg=read_config(config_path); site=cfg["site"]; crawl=cfg["crawl"]
    agent=crawl.get("user_agent","SEOWorker/0.1 (+https://example.invalid/seo-worker)")
    f=PoliteFetcher(agent,float(crawl.get("delay_seconds",1)),float(crawl.get("timeout_seconds",15)),bool(crawl.get("respect_robots",True)))
    urls=discover_urls(site["url"],f,int(crawl["max_pages"]))
    pages=[]
    # Avoid fetching root twice if it was used for discovery by allowing crawl pages to remeasure. This is intentional per run.
    for u in urls: pages.append(f.fetch(u))
    issues=audit(pages,cfg)
    origin=urllib.parse.urlsplit(site["url"])
    base=f"{origin.scheme}://{origin.netloc}"
    for path, label in (("/robots.txt", "robots"), ("/sitemap.xml", "sitemap"), ("/llms.txt", "llms_txt")):
        resource=f"{base}{path}"
        resource_page=f.fetch(resource)
        if resource_page.status == 404 or resource_page.error and "404" in resource_page.error:
            issues.append({"url":resource,"severity":"low","category":label,"message":f"{path} returned 404.","suggestion":f"Review whether {path} is useful for this site."})
    applied=apply_local_fixes(repo,pages,site["url"]) if apply and repo else []
    gaps=content_gaps(cfg,pages); issues.extend({"url":site["url"],"severity":"low","category":g["type"],"message":g["message"],"suggestion":"Review the configured template and seed pages."} for g in gaps)
    db=Path(crawl.get("database",".seo-worker/state.sqlite3")); rid=persist(db,pages,issues)
    sev=Counter(i["severity"] for i in issues); cat=Counter(i["category"] for i in issues)
    cmpd=compare_previous(db,rid,pages,issues)
    summary={"schema_version":1,"site":site["url"],"site_name":site.get("name",""),"run_id":rid,"generated_at":datetime.now(timezone.utc).isoformat(),"pages_crawled":len(pages),"findings_total":len(issues),"findings_by_severity":dict(sev),"findings_by_category":dict(cat),"new_findings":cmpd.get("new_findings") if cmpd.get("available") else None,"resolved_findings":cmpd.get("resolved_findings") if cmpd.get("available") else None,"search_console_connected":bool(os.environ.get("GSC_ACCESS_TOKEN"))}
    data={"summary":summary,"run_id":rid,"site":site["url"],"generated_at":datetime.now(timezone.utc).isoformat(),"pages":[asdict(p) for p in pages],"issues":issues,"content_gaps":gaps,"history":history(db),"comparison":cmpd,"suggestions":suggestions(pages,repo),"applied_local_fixes":applied,"apply_mode":bool(apply),**optional_integrations(cfg,urls)}
    output_dir.mkdir(parents=True,exist_ok=True)
    (output_dir/"report.json").write_text(json.dumps(data,indent=2),encoding="utf-8")
    lines=[f"# SEO report: {site.get('name',site['url'])}","",f"Run {rid} · {len(pages)} pages · {len(issues)} findings","", "## Findings", ""]
    if issues:
        for i in sorted(issues,key=lambda x:{"critical":0,"high":1,"medium":2,"low":3}.get(x["severity"],4)):
            lines.append(f"- **{i['severity'].upper()} · {i['category']}** [{i['url']}]({i['url']}): {i['message']}"+(f" Suggested next step: {i['suggestion']}" if i.get("suggestion") else ""))
    else: lines.append("No rule findings for the pages crawled.")
    lines += ["", "## Comparison with previous run", ""]
    cmp=data["comparison"]
    if cmp["available"]:
        lines.append(f"Compared with run {cmp['previous_run_id']}: {cmp['issue_count_delta']:+d} findings, {cmp['resolved_findings']} resolved, {cmp['new_findings']} new; {len(cmp['changed_page_metrics'])} pages changed status or metadata.")
    else:
        lines.append("No earlier run is available for comparison.")
    lines += ["", "## Integration status", ""]
    for k,v in data["integrations"].items(): lines.append(f"- {k}: {v}")
    lines += ["", "## Local changes", ""]
    if data["applied_local_fixes"]:
        lines.extend(f"- {item['change']} in `{item['path']}` ({item['url']})" for item in data["applied_local_fixes"])
    else:
        lines.append("No local source files changed.")
    lines += ["", "## Safety", "", "The crawler never changes the live site. Apply mode only adds missing canonical tags to exact-match static HTML files inside the supplied local repository.",""]
    (output_dir/"report.md").write_text("\n".join(lines),encoding="utf-8")
    items="".join('<li><b>%s · %s</b> <a href="%s">%s</a>: %s</li>'%(html.escape(i["severity"]),html.escape(i["category"]),html.escape(i["url"],quote=True),html.escape(i["url"]),html.escape(i["message"])) for i in issues)
    html_report="<!doctype html><meta charset='utf-8'><title>SEO report</title><style>body{font:16px system-ui;max-width:1000px;margin:3rem auto;padding:0 1rem}li{margin:.7rem 0}</style><h1>SEO report</h1><p>Run %s · %d pages · %d findings</p><ul>%s</ul>"%(rid,len(pages),len(issues),items)
    (output_dir/"report.html").write_text(html_report,encoding="utf-8")
    return data
