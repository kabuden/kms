"""미국 시장 경제뉴스 수집 에이전트 (수집 에이전트 #1)."""
from __future__ import annotations

from .base_collector import BaseCollector


class USMarketCollector(BaseCollector):
    name = "us-collector"
    market = "US"
    description = "미국 시장 경제뉴스 및 애널리스트 의견 수집"

    lang = "en"
    gl = "US"
    feeds = [
        # 1순위: Google News(안정적). 2순위: 직접 피드(가능하면 추가 수집)
        ("GoogleNews 시장", "https://news.google.com/rss/search?q=US%20stock%20market%20when:1d&hl=en-US&gl=US&ceid=US:en"),
        ("CNBC Markets", "https://www.cnbc.com/id/20910258/device/rss/rss.html"),
        ("MarketWatch", "https://feeds.content.dowjones.io/public/rss/mw_topstories"),
    ]

