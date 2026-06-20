"""LLM 게이트웨이 — 외부 추론 백엔드(Groq)를 감싸는 패키지.

하네스(강세·약세·심판 토론 + 회고 루프)가 사용하는 추론 호출을 한곳에 모은다.
키가 없거나 호출이 실패하면 호출부가 휴리스틱으로 폴백할 수 있도록 None 을 돌려준다.
"""
from .groq_client import GroqClient, groq_available

__all__ = ["GroqClient", "groq_available"]
