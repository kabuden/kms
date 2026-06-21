"""한국 시장 경제뉴스 수집 에이전트 (수집 에이전트 #2)."""
from __future__ import annotations

from .base_collector import BaseCollector


class KRMarketCollector(BaseCollector):
    name = "kr-collector"
    market = "KR"
    description = "한국 시장 경제뉴스 및 애널리스트 의견 수집"

    lang = "ko"
    gl = "KR"
    feeds = [
        # 1순위: Google News(안정적). 2순위: 직접 피드(가능하면 추가 수집)
        ("GoogleNews 증시", "https://news.google.com/rss/search?q=%EC%A6%9D%EC%8B%9C%20%EC%BD%94%EC%8A%A4%ED%94%BC%20when:1d&hl=ko&gl=KR&ceid=KR:ko"),
        ("한국경제", "https://www.hankyung.com/feed/finance"),
        ("연합뉴스 경제", "https://www.yna.co.kr/rss/economy.xml"),
    ]

