"""한국 시장 경제뉴스 수집 에이전트 (수집 에이전트 #2)."""
from __future__ import annotations

from .base_collector import BaseCollector


class KRMarketCollector(BaseCollector):
    name = "kr-collector"
    market = "KR"
    description = "한국 시장 경제뉴스 및 애널리스트 의견 수집"

    feeds = [
        ("연합인포맥스", "https://news.einfomax.co.kr/rss/allArticle.xml"),
        ("한경", "https://www.hankyung.com/feed/finance"),
    ]

    headline_templates = [
        "코스피 외국인 순매수에 강세… 반도체주 급등",
        "원/달러 환율 상승, 수출주 우려 부각",
        "삼성전자 메모리 업황 개선 기대감에 상승",
        "한국은행 금리 동결, 시장 호재로 작용",
        "2차전지 업종 부진… 실적 우려에 약세",
    ]
