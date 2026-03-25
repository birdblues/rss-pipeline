# RSS 매크로 뉴스 파이프라인 — Claude Code 핸드오프

## 프로젝트 개요

매크로/투자 관점의 RSS 피드를 수집하여 Supabase에 저장하는 파이프라인 구축.
MT Newswires MCP 연동은 계정 이슈 해결 후 별도 통합 예정.

## 아키텍처

```
OPML 파일 → feedparser로 RSS 파싱 → 각 item 저장
                                      ↓
                              본문 추출 (우선순위)
                              1. RSS 자체 본문
                              2. Trafilatura (웹 본문 추출)
                              3. Firecrawl (동적 페이지 fallback)
                                      ↓
                              Supabase upsert (article_url unique)
```

---

## 1. Supabase 테이블 스키마

```sql
create table if not exists public.rss_articles (
  id bigint generated always as identity primary key,
  feed_title text,
  feed_url text not null,
  item_guid text,
  article_url text not null,
  title text,
  author text,
  published_at timestamptz,
  summary text,
  content_text text,
  content_html text,
  source_domain text,
  lang text,
  extracted_via text,        -- 'rss_embedded' | 'trafilatura' | 'firecrawl'
  rss_raw jsonb,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create unique index if not exists rss_articles_article_url_key
  on public.rss_articles(article_url);

create unique index if not exists rss_articles_guid_key
  on public.rss_articles(item_guid)
  where item_guid is not null;
```

---

## 2. OPML 피드 구성

### Core Macro (기관 — RSS 본문 포함률 높음, 무료)

| 카테고리 | 매체 | RSS URL |
|---------|------|---------|
| 중앙은행 | Federal Reserve | https://www.federalreserve.gov/feeds/press_all.xml |
| 중앙은행 | Fed Speeches | https://www.federalreserve.gov/feeds/speeches.xml |
| 중앙은행 | ECB | https://www.ecb.europa.eu/rss/press.html |
| 중앙은행 | ECB Speeches | https://www.ecb.europa.eu/rss/speeches.html |
| 중앙은행 | BOJ | https://www.boj.or.jp/en/rss/announcements.xml |
| 중앙은행 | Bank of England | https://www.bankofengland.co.uk/rss/news |
| 중앙은행 | St. Louis Fed | https://www.stlouisfed.org/feeds/news.xml |
| 중앙은행 | Dallas Fed | https://www.dallasfed.org/rss |
| 국제기구 | IMF News | https://www.imf.org/en/News/rss |
| 국제기구 | IMF Blog | https://blogs.imf.org/feed/ |
| 국제기구 | World Bank | https://www.worldbank.org/en/news/rss |
| 국제기구 | BIS Press | https://www.bis.org/press/rss.xml |
| 국제기구 | BIS Speeches | https://www.bis.org/speeches/index.htm?rss=1 |
| 국제기구 | OECD | https://www.oecd.org/newsroom/rss.xml |
| 경제지표 | BLS (CPI/고용) | https://www.bls.gov/feed/bls_latest.rss |
| 경제지표 | BEA (GDP) | https://www.bea.gov/rss/rss.xml |
| 원자재 | EIA | https://www.eia.gov/rss/ |
| 원자재 | OPEC | https://www.opec.org/opec_web/en/press_room/rss.xml |

### Market Sentiment (뉴스 속보 — 요약 위주)

| 매체 | RSS URL |
|------|---------|
| Reuters Business | https://www.reutersagency.com/feed/?best-topics=business-finance |
| Bloomberg Markets | https://feeds.bloomberg.com/markets/news.rss |
| CNBC | https://www.cnbc.com/id/100003114/device/rss/rss.html |
| Yahoo Finance | https://finance.yahoo.com/rss/topstories |
| MarketWatch | http://feeds.marketwatch.com/marketwatch/topstories/ |
| Investing.com | https://www.investing.com/rss/news.rss |

### 한국 경제

| 매체 | RSS URL |
|------|---------|
| 연합뉴스 경제 | https://www.yna.co.kr/rss/economy.xml |
| 매일경제 | https://www.mk.co.kr/rss/30100041/ |
| 한국경제 | https://www.hankyung.com/feed/economy |
| 조선비즈 | https://biz.chosun.com/arc/outboundfeeds/rss/?outputType=xml |
| 머니투데이 | https://rss.mt.co.kr/mt_news.xml |

---

## 3. OPML 파일

`feeds.opml` 로 저장:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<opml version="2.0">
  <head><title>Macro Investment Feeds</title></head>
  <body>

    <outline text="Central Banks">
      <outline text="Federal Reserve" xmlUrl="https://www.federalreserve.gov/feeds/press_all.xml"/>
      <outline text="Fed Speeches" xmlUrl="https://www.federalreserve.gov/feeds/speeches.xml"/>
      <outline text="ECB" xmlUrl="https://www.ecb.europa.eu/rss/press.html"/>
      <outline text="ECB Speeches" xmlUrl="https://www.ecb.europa.eu/rss/speeches.html"/>
      <outline text="BOJ" xmlUrl="https://www.boj.or.jp/en/rss/announcements.xml"/>
      <outline text="Bank of England" xmlUrl="https://www.bankofengland.co.uk/rss/news"/>
      <outline text="St. Louis Fed" xmlUrl="https://www.stlouisfed.org/feeds/news.xml"/>
      <outline text="Dallas Fed" xmlUrl="https://www.dallasfed.org/rss"/>
    </outline>

    <outline text="International Orgs">
      <outline text="IMF News" xmlUrl="https://www.imf.org/en/News/rss"/>
      <outline text="IMF Blog" xmlUrl="https://blogs.imf.org/feed/"/>
      <outline text="World Bank" xmlUrl="https://www.worldbank.org/en/news/rss"/>
      <outline text="BIS Press" xmlUrl="https://www.bis.org/press/rss.xml"/>
      <outline text="BIS Speeches" xmlUrl="https://www.bis.org/speeches/index.htm?rss=1"/>
      <outline text="OECD" xmlUrl="https://www.oecd.org/newsroom/rss.xml"/>
    </outline>

    <outline text="Economic Data">
      <outline text="BLS" xmlUrl="https://www.bls.gov/feed/bls_latest.rss"/>
      <outline text="BEA" xmlUrl="https://www.bea.gov/rss/rss.xml"/>
      <outline text="EIA" xmlUrl="https://www.eia.gov/rss/"/>
      <outline text="OPEC" xmlUrl="https://www.opec.org/opec_web/en/press_room/rss.xml"/>
    </outline>

    <outline text="Markets">
      <outline text="Reuters Business" xmlUrl="https://www.reutersagency.com/feed/?best-topics=business-finance"/>
      <outline text="Bloomberg Markets" xmlUrl="https://feeds.bloomberg.com/markets/news.rss"/>
      <outline text="CNBC" xmlUrl="https://www.cnbc.com/id/100003114/device/rss/rss.html"/>
      <outline text="Yahoo Finance" xmlUrl="https://finance.yahoo.com/rss/topstories"/>
      <outline text="MarketWatch" xmlUrl="http://feeds.marketwatch.com/marketwatch/topstories/"/>
      <outline text="Investing.com" xmlUrl="https://www.investing.com/rss/news.rss"/>
    </outline>

    <outline text="Korea">
      <outline text="연합뉴스 경제" xmlUrl="https://www.yna.co.kr/rss/economy.xml"/>
      <outline text="매일경제" xmlUrl="https://www.mk.co.kr/rss/30100041/"/>
      <outline text="한국경제" xmlUrl="https://www.hankyung.com/feed/economy"/>
      <outline text="조선비즈" xmlUrl="https://biz.chosun.com/arc/outboundfeeds/rss/?outputType=xml"/>
      <outline text="머니투데이" xmlUrl="https://rss.mt.co.kr/mt_news.xml"/>
    </outline>

  </body>
</opml>
```

---

## 4. Python 코드

### 설치

```bash
pip install feedparser beautifulsoup4 python-dotenv requests supabase trafilatura lxml dateutil
# Firecrawl 보조 (선택):
pip install firecrawl-py
```

### .env

```bash
SUPABASE_URL=https://YOUR_PROJECT.supabase.co
SUPABASE_KEY=YOUR_SERVICE_ROLE_KEY
FIRECRAWL_API_KEY=fc-xxxxxxxx   # 선택
USER_AGENT=MacroRSSCollector/1.0
REQUEST_TIMEOUT=20
```

### rss_to_supabase.py

```python
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
from supabase import create_client, Client

try:
    from firecrawl import FirecrawlApp
except Exception:
    FirecrawlApp = None


load_dotenv()

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY")
USER_AGENT = os.getenv("USER_AGENT", "MacroRSSCollector/1.0")
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "20"))

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# 기관 RSS는 본문이 가장 정확하므로 외부 추출 스킵
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

# 도메인별 rate limit (초)
DOMAIN_SLEEP = {
    "default": 1.0,
    "www.federalreserve.gov": 2.0,
    "www.imf.org": 2.0,
    "www.bls.gov": 2.0,
}

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


@dataclass
class FeedSource:
    title: str
    xml_url: str
    html_url: Optional[str] = None
    category: Optional[str] = None


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


def safe_get(d: dict, *keys, default=None):
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return default


def parse_date(date_str: Optional[str]) -> Optional[str]:
    """published_at를 ISO 8601 timestamptz로 정규화"""
    if not date_str:
        return None
    try:
        dt = dateparser.parse(date_str)
        return dt.isoformat()
    except Exception:
        return None


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


def extract_with_trafilatura(url: str) -> Dict[str, Optional[str]]:
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


def normalize_guid(entry: dict, link: str) -> Optional[str]:
    guid = safe_get(entry, "id", "guid", default=None)
    if guid:
        return str(guid)
    if link:
        return hashlib.sha256(link.encode("utf-8")).hexdigest()
    return None


def choose_best_content(
    rss_content: Dict[str, Optional[str]],
    extracted: Dict[str, Optional[str]],
    extracted_fallback: Dict[str, Optional[str]],
    is_institutional: bool,
) -> Dict[str, Optional[str]]:
    """
    우선순위 (개선):
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

    for candidate in [extracted, extracted_fallback]:
        if candidate.get("content_text") and len(candidate["content_text"]) > 300:
            return {
                "content_text": candidate["content_text"],
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


def batch_upsert(rows: List[Dict[str, Any]]) -> None:
    """피드 단위로 모아서 bulk upsert"""
    if not rows:
        return
    supabase.table("rss_articles").upsert(
        rows, on_conflict="article_url"
    ).execute()


def get_sleep_for_domain(domain: str) -> float:
    return DOMAIN_SLEEP.get(domain, DOMAIN_SLEEP["default"])


def process_feed(source: FeedSource) -> int:
    parsed = feedparser.parse(source.xml_url)
    rows: List[Dict[str, Any]] = []

    for entry in parsed.entries:
        link = safe_get(entry, "link", default=None)
        if not link:
            continue

        domain = urlparse(link).netloc.lower()
        is_institutional = domain in INSTITUTIONAL_DOMAINS

        rss_content = extract_text_from_rss_entry(entry)

        # 기관 RSS는 본문이 충분하면 외부 추출 스킵
        extracted = {"content_text": None, "content_html": None, "author": None,
                     "published_at": None, "lang": None, "extracted_via": None}
        extracted_fallback = extracted.copy()

        if not (is_institutional and rss_content.get("content_text") and len(rss_content["content_text"] or "") > 100):
            extracted = extract_with_trafilatura(link)
            if not extracted.get("content_text"):
                extracted_fallback = extract_with_firecrawl(link)
            time.sleep(get_sleep_for_domain(domain))

        best = choose_best_content(rss_content, extracted, extracted_fallback, is_institutional)

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

    # bulk upsert per feed
    batch_upsert(rows)
    return len(rows)


def main(opml_path: str):
    sources = parse_opml(opml_path)
    print(f"Loaded {len(sources)} feeds from OPML")

    total = 0
    for i, source in enumerate(sources, 1):
        print(f"[{i}/{len(sources)}] {source.title} — {source.xml_url}")
        try:
            n = process_feed(source)
            total += n
            print(f"  -> {n} items upserted")
        except Exception as e:
            print(f"  !! failed: {e}")

    print(f"\nDone. Total: {total} items")


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python rss_to_supabase.py feeds.opml")
        raise SystemExit(1)
    main(sys.argv[1])
```

---

## 5. 원본 코드 대비 개선사항

이미 반영된 것:

| 항목 | 원본 | 개선 |
|------|------|------|
| 본문 추출 우선순위 | trafilatura > RSS 항상 | 기관 RSS는 본문 우선, 뉴스는 외부 추출 우선 (`INSTITUTIONAL_DOMAINS` 분기) |
| rate limiting | `time.sleep(1.0)` 하드코딩 | 도메인별 sleep (`DOMAIN_SLEEP` dict) |
| published_at 파싱 | feedparser 원본 문자열 그대로 | `dateutil.parser`로 ISO 8601 정규화 |
| DB upsert | 건건이 upsert | 피드 단위 `batch_upsert` |
| 기관 RSS 불필요 fetch | 항상 trafilatura 시도 | `is_institutional` 체크로 스킵 |

---

## 6. 추가 구현 TODO

Claude Code에서 이어서 할 작업:

- [ ] Supabase에 테이블 생성 (위 SQL 실행)
- [ ] .env 파일에 실제 Supabase 크레덴셜 세팅
- [ ] `feeds.opml` 저장 및 첫 실행 테스트
- [ ] RSS 피드 중 실제로 본문이 안 오거나 접근 불가인 피드 확인 후 리스트 정리
  - Bloomberg RSS는 사실상 비어있을 가능성 높음
  - Reuters RSS도 지연/제한 있을 수 있음
- [ ] cron / GitHub Actions로 주기 실행 (10분~1시간)
- [ ] MT Newswires 계정 문제 해결 후 MCP 데이터 통합
  - 데이터셋: `mt_newswires_north_america`, `mt_newswires_global` (product: edge)
  - 필드: headline, body, key(ticker), metadata, releaseTime, storyType
  - MT Newswires 데이터를 같은 `rss_articles` 테이블에 넣거나 별도 테이블 분리 결정 필요
- [ ] (선택) LangChain 임베딩 연동 — 수집된 기사를 벡터화하여 semantic search
- [ ] (선택) Finlight API 보완 — RSS로 못 잡는 실시간 마켓 속보용 ($29/월, 10K req + 5K websocket)

---

## 7. MT Newswires MCP 참고

현재 상태: 구독 완료, MCP 연결 완료, 메타데이터 API 작동, **데이터 fetch 시 에러 (계정 이슈 추정)**

MT Newswires에 support 이메일 발송 필요 (GENERAL INQUIRIES).
요점: "Claude MCP 커넥터 연결은 되지만 데이터 fetch 시 HTTPStatusError / Permission denied 발생. 구독과 연결된 계정 확인 요청."

### MCP 도구 구조

```
MT Newswires:search       — 데이터셋 목록 조회
MT Newswires:fetch         — 뉴스 데이터 조회 (dataset_name, endpoint, product, symbols, from_date, to_date, last 등)
MT Newswires:current_date  — 현재 날짜
MT Newswires:get_rules     — 알림 규칙 조회
MT Newswires:create_rule   — 알림 규칙 생성
MT Newswires:delete_rule   — 알림 규칙 삭제
```

### 사용 가능한 데이터셋

- `mt_newswires_north_america` (edge) — 미국/캐나다 마켓
- `mt_newswires_global` (edge) — 글로벌 (NA + EMEA + APAC)

### 필드 구조

```
headline      — 기사 제목 (항상 존재)
body          — 본문 (headline-only 기사는 null)
key           — 주요 티커
related       — 관련 티커 목록
metadata      — 카테고리 태그 (stocks, economics 등)
releaseTime   — UTC ISO 8601 발행 시각
storyType     — Regular-Session / Extended-Hours
isPrimary     — 해당 티커가 기사의 주요 대상인지
```

---

## 8. 비용 비교 참고

| 서비스 | 비용 | 용도 |
|--------|------|------|
| RSS 파이프라인 | 무료 | 기관 데이터, 매크로 신호, 경제지표 발표 |
| MT Newswires | 구독 (가격 미공개) | 실시간 마켓 속보, 티커별 뉴스 |
| Finlight Pro Light | $29/월 | 실시간 마켓 뉴스 보완 (10K req + 5K websocket/월) |

**전략: RSS(기관/매크로 무료) + MT Newswires(실시간 속보)가 기본. Finlight는 MT Newswires로 충분하면 불필요.**
