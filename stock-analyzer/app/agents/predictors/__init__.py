from .momentum import MomentumPredictor
from .sentiment import SentimentPredictor
from .analyst_consensus import AnalystConsensusPredictor
from .mean_reversion import MeanReversionPredictor
from .llm_reasoner import LLMReasonerPredictor

# 예측 에이전트 5인 (각기 다른 방식)
ALL_PREDICTORS = [
    MomentumPredictor,
    SentimentPredictor,
    AnalystConsensusPredictor,
    MeanReversionPredictor,
    LLMReasonerPredictor,
]

__all__ = ["ALL_PREDICTORS", "MomentumPredictor", "SentimentPredictor",
           "AnalystConsensusPredictor", "MeanReversionPredictor",
           "LLMReasonerPredictor"]
