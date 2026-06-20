from .momentum import MomentumPredictor
from .sentiment import SentimentPredictor
from .analyst_consensus import AnalystConsensusPredictor
from .mean_reversion import MeanReversionPredictor
from .llm_reasoner import LLMReasonerPredictor
from .event_drift import EventDriftPredictor
from .value import ValuePredictor
from .quality import QualityPredictor
from .low_volatility import LowVolatilityPredictor
from .sector_spillover import SectorSpilloverPredictor

# 예측 에이전트 10인 (각기 다른 방식)
ALL_PREDICTORS = [
    MomentumPredictor,
    SentimentPredictor,
    AnalystConsensusPredictor,
    MeanReversionPredictor,
    LLMReasonerPredictor,
    EventDriftPredictor,
    ValuePredictor,
    QualityPredictor,
    LowVolatilityPredictor,
    SectorSpilloverPredictor,
]

__all__ = ["ALL_PREDICTORS", "MomentumPredictor", "SentimentPredictor",
           "AnalystConsensusPredictor", "MeanReversionPredictor",
           "LLMReasonerPredictor", "EventDriftPredictor", "ValuePredictor",
           "QualityPredictor", "LowVolatilityPredictor",
           "SectorSpilloverPredictor"]
