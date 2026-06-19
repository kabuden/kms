"""수집 에이전트 베이스 (무료·API키 불필요).

온라인(SA_OFFLINE=false)이면 표준 라이브러리로 RSS를 직접 파싱한다.
  - 시장 전반 뉴스: 각 시장의 경제뉴스 RSS(피드 목록)
  - 종목별 뉴스: Yahoo Finance 종목별 헤드라인 RSS
RSS는 '현재' 뉴스만 제공하므로, 과거 cycle_date(시드/백테스트)에는 뉴스를
수집하지 않는다(없는 과거 뉴스를 지어내지 않음). 오프라인이면 합성 뉴스.
"""
from __future__ import annotations

import hashlib
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime

from ...config import SETTINGS, TickerSpec
from ...models import AnalystView, NewsItem
from ..base import Agent

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")


def google_news_url(query: str, lang: str, gl: str) -> str:
    """Google News RSS 검색 URL. 키 불필요, 다국어, 비교적 안정적."""
    q = urllib.parse.quote(query)
    return (f"https://news.google.com/rss/search?q={q}"
            f"&hl={lang}&gl={gl}&ceid={gl}:{lang}")

# 키 없는 감성 사전(영문+국문). LLM 없이도 동작하는 폴백.
_POS = {"surge", "rally", "beat", "beats", "growth", "record", "upgrade", "strong",
        "gain", "gains", "profit", "boom", "jump", "soar", "optimism", "rebound",
        "상승", "호재", "급등", "최대", "개선", "강세", "호조", "반등", "수혜"}
_NEG = {"plunge", "fall", "falls", "miss", "misses", "cut", "downgrade", "weak",
        "loss", "losses", "fear", "recession", "slump", "drop", "tumble", "warn",
        "하락", "악재", "급락", "부진", "우려", "약세", "감소", "충격", "둔화"}


def lexicon_sentiment(text: str) -> float:
    t = text.lower()
    pos = sum(1 for w in _POS if w in t)
    neg = sum(1 for w in _NEG if w in t)
    total = pos + neg
    return round((pos - neg) / total, 3) if total else 0.0


def _is_recent(cycle_date: str, days: int = 3) -> bool:
    try:
        d = datetime.fromisoformat(cycle_date).date()
    except ValueError:
        return False
    return (date.today() - d).days <= days


def _seed_int(*parts: str) -> int:
    return int(hashlib.sha256(":".join(parts).encode()).hexdigest()[:8], 16)


def _fetch_rss(url: str, source: str, market: str, symbol: str = "",
               limit: int = 12) -> list[NewsItem]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=10) as resp:
            root = ET.fromstring(resp.read())
    except Exception:
        return []
    items: list[NewsItem] = []
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        if not title:
            continue
        desc = (it.findtext("description") or "").strip()
        items.append(NewsItem(
            market=market, source=source, title=title, summary=desc[:500],
            url=(it.findtext("link") or "").strip(),
            published_at=(it.findtext("pubDate") or "").strip(),
            sentiment=lexicon_sentiment(title + " " + desc), symbol=symbol,
        ))
        if len(items) >= limit:
            break
    return items


class BaseCollector(Agent):
    role = "collector"
    market = "US"
    feeds: list[tuple[str, str]] = []   # (source_name, rss_url) 직접 피드(추가 다양성)
    headline_templates: list[str] = []  # 오프라인 합성용
    lang = "en"                         # Google News 언어
    gl = "US"                           # Google News 국가

    def _ticker_query(self, spec: TickerSpec) -> str:
        """종목별 뉴스 검색어. 한국은 종목명, 미국은 티커 기준."""
        return f"{spec.name} 주가" if self.market == "KR" else f"{spec.symbol} stock"

    # ── 시장 전반 뉴스 ──
    def collect_news(self, cycle_date: str) -> list[NewsItem]:
        if SETTINGS.offline:
            return self._synthetic_news(cycle_date)
        if not _is_recent(cycle_date):
            return []   # 과거 날짜: RSS로 과거 뉴스를 가져올 수 없음
        items: list[NewsItem] = []
        for source, url in self.feeds:
            items += _fetch_rss(url, source, self.market)
        return items

    # ── 종목별 뉴스 (Google News 검색) ──
    def collect_ticker_news(self, cycle_date: str, spec: TickerSpec) -> list[NewsItem]:
        if SETTINGS.offline or not _is_recent(cycle_date):
            return []
        if spec.symbol.startswith("^"):   # 지수는 종목 헤드라인 생략
            return []
        url = google_news_url(self._ticker_query(spec), self.lang, self.gl)
        return _fetch_rss(url, f"GoogleNews:{spec.name}", self.market,
                          spec.symbol, limit=8)

    def _synthetic_news(self, cycle_date: str) -> list[NewsItem]:
        items: list[NewsItem] = []
        for i, tmpl in enumerate(self.headline_templates):
            s = _seed_int(self.market, cycle_date, str(i))
            sentiment = round(((s % 2000) / 1000.0 - 1.0), 3)
            items.append(NewsItem(
                market=self.market, source=f"{self.market}-wire",
                title=tmpl, summary=tmpl,
                url=f"https://example.com/{self.market}/{cycle_date}/{i}",
                published_at=cycle_date, sentiment=sentiment,
            ))
        return items

    # ── 애널리스트 의견 (현재는 합성: 무료 실데이터 소스가 제한적) ──
    def collect_analyst_views(self, cycle_date: str) -> list[AnalystView]:
        firms = ["Goldman", "Morgan", "JPMorgan", "Mirae", "Samsung Sec"]
        views: list[AnalystView] = []
        for spec in SETTINGS.market_symbols(self.market):
            for firm in firms:
                s = _seed_int(firm, spec.symbol, cycle_date)
                bucket = s % 100
                if bucket < 45:
                    rating, tgt = "buy", round((s % 800) / 100.0, 2)
                elif bucket < 75:
                    rating, tgt = "hold", round((s % 200) / 100.0 - 1.0, 2)
                else:
                    rating, tgt = "sell", round(-((s % 600) / 100.0), 2)
                views.append(AnalystView(self.market, firm, spec.symbol, rating, tgt))
        return views
