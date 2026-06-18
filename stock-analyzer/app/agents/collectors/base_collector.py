"""수집 에이전트 베이스.

온라인이면 RSS 피드에서 경제뉴스를 수집하고, 오프라인/실패 시
결정론적 합성 뉴스로 폴백한다. 동시에 해당 시장 종목들에 대한
애널리스트 의견(등급/목표가)도 합성/수집한다.
"""
from __future__ import annotations

import hashlib
from datetime import datetime

from ...config import SETTINGS, TickerSpec
from ...models import AnalystView, NewsItem
from ..base import Agent

# 아주 가벼운 감성 사전 (LLM 없이도 동작하는 폴백)
_POS = {"surge", "rally", "beat", "growth", "record", "upgrade", "strong",
        "gain", "profit", "boom", "상승", "호재", "급등", "최대", "개선", "강세"}
_NEG = {"plunge", "fall", "miss", "cut", "downgrade", "weak", "loss", "fear",
        "recession", "slump", "하락", "악재", "급락", "부진", "우려", "약세"}


def lexicon_sentiment(text: str) -> float:
    t = text.lower()
    pos = sum(1 for w in _POS if w in t)
    neg = sum(1 for w in _NEG if w in t)
    total = pos + neg
    if total == 0:
        return 0.0
    return round((pos - neg) / total, 3)


def _seed_int(*parts: str) -> int:
    return int(hashlib.sha256(":".join(parts).encode()).hexdigest()[:8], 16)


class BaseCollector(Agent):
    role = "collector"
    market = "US"
    feeds: list[tuple[str, str]] = []  # (source_name, rss_url)

    # 합성 뉴스 템플릿 (오프라인 데모용)
    headline_templates: list[str] = []

    def collect_news(self, cycle_date: str) -> list[NewsItem]:
        if not SETTINGS.offline and self.feeds:
            items = self._collect_rss(cycle_date)
            if items:
                return items
        return self._synthetic_news(cycle_date)

    def _collect_rss(self, cycle_date: str) -> list[NewsItem]:
        try:
            import feedparser  # type: ignore
        except Exception:
            return []
        items: list[NewsItem] = []
        for source, url in self.feeds:
            try:
                parsed = feedparser.parse(url)
            except Exception:
                continue
            for e in parsed.entries[:10]:
                title = getattr(e, "title", "")
                summary = getattr(e, "summary", "")
                items.append(NewsItem(
                    market=self.market, source=source, title=title,
                    summary=summary[:500], url=getattr(e, "link", ""),
                    published_at=getattr(e, "published", cycle_date),
                    sentiment=lexicon_sentiment(title + " " + summary),
                ))
        return items

    def _synthetic_news(self, cycle_date: str) -> list[NewsItem]:
        items: list[NewsItem] = []
        for i, tmpl in enumerate(self.headline_templates):
            s = _seed_int(self.market, cycle_date, str(i))
            sentiment = round(((s % 2000) / 1000.0 - 1.0), 3)  # -1 ~ +1
            items.append(NewsItem(
                market=self.market, source=f"{self.market}-wire",
                title=tmpl, summary=tmpl,
                url=f"https://example.com/{self.market}/{cycle_date}/{i}",
                published_at=cycle_date, sentiment=sentiment,
            ))
        return items

    def collect_analyst_views(self, cycle_date: str) -> list[AnalystView]:
        """시장 내 종목별 애널리스트 의견(합성/결정론)."""
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
