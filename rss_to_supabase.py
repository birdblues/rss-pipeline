import os
import json
import time
import hashlib
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from urllib.parse import urlparse

import feedparser
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from dateutil import parser as dateparser
import trafilatura

try:
    from firecrawl import FirecrawlApp
except Exception:
    FirecrawlApp = None

try:
    from playwright.sync_api import sync_playwright
except Exception:
    sync_playwright = None


load_dotenv()


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY")
USER_AGENT = os.getenv("USER_AGENT", "MacroRSSCollector/1.0")
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "20"))

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

INSTITUTIONAL_DOMAINS = {
    "www.federalreserve.gov",
    "www.ecb.europa.eu",
    "www.boj.or.jp",
    "www.bankofengland.co.uk",
    "www.imf.org",
    "blogs.imf.org",
    "www.worldbank.org",
    "www.bis.org",
    "www.oecd.org",
    "www.bls.gov",
    "www.bea.gov",
    "www.stlouisfed.org",
    "www.dallasfed.org",
}

DOMAIN_SLEEP: Dict[str, float] = {
    "default": 1.0,
    "www.federalreserve.gov": 2.0,
    "www.imf.org": 2.0,
    "www.bls.gov": 2.0,
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class FeedSource:
    title: str
    xml_url: str
    html_url: Optional[str] = None
    category: Optional[str] = None


# ---------------------------------------------------------------------------
# OPML parser
# ---------------------------------------------------------------------------

def parse_opml(opml_path: str) -> List[FeedSource]:
    tree = ET.parse(opml_path)
    root = tree.getroot()
    sources: List[FeedSource] = []

    def walk(node, current_category=None):
        for outline in node.findall("outline"):
            text = outline.attrib.get("text") or outline.attrib.get("title") or ""
            xml_url = outline.attrib.get("xmlUrl")
            html_url = outline.attrib.get("htmlUrl")
            if xml_url:
                sources.append(
                    FeedSource(
                        title=text.strip(),
                        xml_url=xml_url.strip(),
                        html_url=html_url.strip() if html_url else None,
                        category=current_category,
                    )
                )
            else:
                walk(outline, current_category=text.strip() or current_category)

    body = root.find("body")
    if body is not None:
        walk(body)
    return sources


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def safe_get(d: dict, *keys, default=None):
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return default


def parse_date(date_str: Optional[str]) -> Optional[str]:
    if not date_str:
        return None
    try:
        dt = dateparser.parse(date_str)
        return dt.isoformat()
    except Exception:
        return None


def normalize_guid(entry: dict, link: str) -> Optional[str]:
    guid = safe_get(entry, "id", "guid", default=None)
    if guid:
        return str(guid)
    if link:
        return hashlib.sha256(link.encode("utf-8")).hexdigest()
    return None


def get_sleep_for_domain(domain: str) -> float:
    return DOMAIN_SLEEP.get(domain, DOMAIN_SLEEP["default"])


# ---------------------------------------------------------------------------
# Content extraction
# ---------------------------------------------------------------------------

def extract_text_from_rss_entry(entry: dict) -> Dict[str, Optional[str]]:
    """RSS/Atom 자체에 본문이 있으면 우선 사용."""
    summary = safe_get(entry, "summary", "description", default=None)
    content_html = None
    content_text = None

    if "content" in entry and entry["content"]:
        first = entry["content"][0]
        content_html = first.get("value")
    elif summary:
        content_html = summary

    if content_html:
        soup = BeautifulSoup(content_html, "html.parser")
        content_text = soup.get_text("\n", strip=True)

    return {
        "summary": summary,
        "content_html": content_html,
        "content_text": content_text,
    }


BLOCK_MARKERS = [
    "not a robot", "captcha", "are you human", "access denied",
    "enable javascript", "please verify", "checking your browser",
    "just a moment", "cloudflare",
]


def _is_blocked_page(text: Optional[str]) -> bool:
    if not text or len(text) > 2000:
        return False
    lower = text.lower()
    return any(m in lower for m in BLOCK_MARKERS)


def fetch_html(url: str) -> Optional[str]:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        ctype = resp.headers.get("Content-Type", "")
        if "text/html" not in ctype and "application/xhtml+xml" not in ctype:
            return None
        return resp.text
    except Exception:
        return None


def fetch_html_with_playwright(url: str) -> Optional[str]:
    """Playwright로 동적 페이지 렌더링 후 HTML 추출."""
    if sync_playwright is None:
        return None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=USER_AGENT)
            page.goto(url, timeout=REQUEST_TIMEOUT * 1000, wait_until="domcontentloaded")
            html = page.content()
            browser.close()
            return html
    except Exception:
        return None


def extract_with_trafilatura(
    url: str, html: Optional[str] = None
) -> Dict[str, Optional[str]]:
    if not html:
        html = fetch_html(url)
    if not html:
        return {"content_text": None, "content_html": None, "author": None,
                "published_at": None, "lang": None, "extracted_via": None}

    text = trafilatura.extract(
        html, url=url, include_comments=False, include_tables=False,
        include_links=False, favor_precision=True, output_format="txt",
    )
    html_clean = trafilatura.extract(
        html, url=url, include_comments=False, include_tables=False,
        include_links=False, favor_precision=True, output_format="html",
    )
    metadata = trafilatura.extract_metadata(html, default_url=url)

    return {
        "content_text": text,
        "content_html": html_clean,
        "author": getattr(metadata, "author", None) if metadata else None,
        "published_at": getattr(metadata, "date", None) if metadata else None,
        "lang": getattr(metadata, "language", None) if metadata else None,
        "extracted_via": "trafilatura" if text else None,
    }


def extract_with_playwright(url: str) -> Dict[str, Optional[str]]:
    """Playwright로 HTML 렌더링 후 trafilatura로 본문 추출."""
    html = fetch_html_with_playwright(url)
    if not html:
        return {"content_text": None, "content_html": None, "author": None,
                "published_at": None, "lang": None, "extracted_via": None}

    result = extract_with_trafilatura(url, html=html)
    if result.get("extracted_via"):
        result["extracted_via"] = "playwright+trafilatura"
    return result


def extract_with_firecrawl(url: str) -> Dict[str, Optional[str]]:
    if not FIRECRAWL_API_KEY or FirecrawlApp is None:
        return {"content_text": None, "content_html": None, "author": None,
                "published_at": None, "lang": None, "extracted_via": None}
    try:
        app = FirecrawlApp(api_key=FIRECRAWL_API_KEY)
        result = app.scrape_url(url, formats=["markdown", "html"])
        data = result if isinstance(result, dict) else {}
        markdown = data.get("markdown")
        html = data.get("html")
        metadata = data.get("metadata", {}) or {}
        return {
            "content_text": markdown,
            "content_html": html,
            "author": metadata.get("author"),
            "published_at": metadata.get("publishedTime") or metadata.get("published_at"),
            "lang": metadata.get("language"),
            "extracted_via": "firecrawl" if (markdown or html) else None,
        }
    except Exception:
        return {"content_text": None, "content_html": None, "author": None,
                "published_at": None, "lang": None, "extracted_via": None}


def choose_best_content(
    rss_content: Dict[str, Optional[str]],
    extracted: Dict[str, Optional[str]],
    extracted_playwright: Dict[str, Optional[str]],
    extracted_fallback: Dict[str, Optional[str]],
    is_institutional: bool,
) -> Dict[str, Optional[str]]:
    """
    우선순위:
    - 기관 RSS: RSS 본문 우선 (가장 정확)
    - 뉴스 RSS: 외부 추출 우선 (RSS는 요약만)
    """
    if is_institutional and rss_content.get("content_text") and len(rss_content["content_text"]) > 100:
        return {
            "content_text": rss_content["content_text"],
            "content_html": rss_content["content_html"],
            "author": None, "published_at": None, "lang": None,
            "extracted_via": "rss_embedded",
        }

    for candidate in [extracted, extracted_playwright, extracted_fallback]:
        ct = candidate.get("content_text")
        if ct and len(ct) > 300 and not _is_blocked_page(ct):
            return {
                "content_text": ct,
                "content_html": candidate["content_html"],
                "author": candidate.get("author"),
                "published_at": candidate.get("published_at"),
                "lang": candidate.get("lang"),
                "extracted_via": candidate.get("extracted_via"),
            }

    return {
        "content_text": rss_content.get("content_text"),
        "content_html": rss_content.get("content_html"),
        "author": None, "published_at": None, "lang": None,
        "extracted_via": "rss_embedded" if rss_content.get("content_text") else None,
    }


# ---------------------------------------------------------------------------
# Supabase
# ---------------------------------------------------------------------------

def get_supabase() -> "Client":
    from supabase import create_client
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def batch_upsert(supabase_client, rows: List[Dict[str, Any]]) -> None:
    if not rows:
        return
    supabase_client.table("rss_articles").upsert(
        rows, on_conflict="article_url"
    ).execute()


# ---------------------------------------------------------------------------
# Feed processing
# ---------------------------------------------------------------------------

_EMPTY_EXTRACTED = {
    "content_text": None, "content_html": None, "author": None,
    "published_at": None, "lang": None, "extracted_via": None,
}


def process_feed(source: FeedSource, supabase_client=None) -> int:
    parsed = feedparser.parse(source.xml_url)
    rows: List[Dict[str, Any]] = []

    for entry in parsed.entries:
        link = safe_get(entry, "link", default=None)
        if not link:
            continue

        domain = urlparse(link).netloc.lower()
        is_institutional = domain in INSTITUTIONAL_DOMAINS

        rss_content = extract_text_from_rss_entry(entry)

        extracted = _EMPTY_EXTRACTED.copy()
        extracted_playwright = _EMPTY_EXTRACTED.copy()
        extracted_fallback = _EMPTY_EXTRACTED.copy()

        # 기관 RSS는 본문이 충분하면 외부 추출 스킵
        if not (is_institutional and rss_content.get("content_text")
                and len(rss_content["content_text"] or "") > 100):
            extracted = extract_with_trafilatura(link)
            if not extracted.get("content_text"):
                extracted_playwright = extract_with_playwright(link)
            if not extracted.get("content_text") and not extracted_playwright.get("content_text"):
                extracted_fallback = extract_with_firecrawl(link)
            time.sleep(get_sleep_for_domain(domain))

        best = choose_best_content(
            rss_content, extracted, extracted_playwright, extracted_fallback, is_institutional
        )

        published_at = parse_date(
            best.get("published_at")
            or safe_get(entry, "published", "updated", default=None)
        )

        row = {
            "feed_title": source.title or safe_get(parsed.feed, "title", default=None),
            "feed_url": source.xml_url,
            "item_guid": normalize_guid(entry, link),
            "article_url": link,
            "title": safe_get(entry, "title", default=None),
            "author": best.get("author") or safe_get(entry, "author", default=None),
            "published_at": published_at,
            "summary": rss_content.get("summary"),
            "content_text": best.get("content_text"),
            "content_html": best.get("content_html"),
            "source_domain": domain,
            "lang": best.get("lang"),
            "extracted_via": best.get("extracted_via"),
            "rss_raw": json.loads(json.dumps(entry, default=str)),
        }
        rows.append(row)

    if supabase_client:
        batch_upsert(supabase_client, rows)
    return len(rows)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(opml_path: str, dry_run: bool = False):
    sources = parse_opml(opml_path)
    print(f"Loaded {len(sources)} feeds from OPML")

    supabase_client = None
    if not dry_run:
        if not SUPABASE_URL or not SUPABASE_KEY:
            print("ERROR: SUPABASE_URL and SUPABASE_KEY must be set in .env")
            raise SystemExit(1)
        supabase_client = get_supabase()

    total = 0
    for i, source in enumerate(sources, 1):
        print(f"[{i}/{len(sources)}] {source.title} — {source.xml_url}")
        try:
            n = process_feed(source, supabase_client)
            total += n
            print(f"  -> {n} items {'collected' if dry_run else 'upserted'}")
        except Exception as e:
            print(f"  !! failed: {e}")

    print(f"\nDone. Total: {total} items")


if __name__ == "__main__":
    import sys
    args = sys.argv[1:]
    dry_run = "--dry-run" in args
    args = [a for a in args if a != "--dry-run"]

    if not args:
        print("Usage: python rss_to_supabase.py [--dry-run] feeds.opml")
        raise SystemExit(1)
    main(args[0], dry_run=dry_run)
