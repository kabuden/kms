"""미국 시장 경제뉴스 수집 에이전트 (수집 에이전트 #1)."""
from __future__ import annotations

from .base_collector import BaseCollector


class USMarketCollector(BaseCollector):
    name = "us-collector"
    market = "US"
    description = "미국 시장 경제뉴스 및 애널리스트 의견 수집"

    feeds = [
        ("CNBC", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664"),
        ("Yahoo Finance", "https://finance.yahoo.com/news/rssindex"),
    ]

    headline_templates = [
        "Fed signals patience as inflation cools; equities rally",
        "Big tech earnings beat estimates, Nasdaq gains",
        "Treasury yields fall on weak jobs data, growth fears linger",
        "Energy sector slumps as oil prices plunge",
        "Semiconductor demand strong, chipmakers upgrade guidance",
    ]
