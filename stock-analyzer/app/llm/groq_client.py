"""Groq 추론 클라이언트 — OpenAI 호환 Chat Completions 를 표준 라이브러리로 호출.

Groq 는 Llama 계열 모델을 매우 빠르게(그리고 저렴하게) 서빙한다. 의존성을 늘리지
않으려고 SDK 대신 urllib 로 직접 호출한다(github_sync.py 와 같은 방침). 키가 없거나
호출이 실패하면 None 을 돌려주어, 하네스가 휴리스틱 앙상블로 안전하게 폴백한다.

환경변수:
  SA_GROQ_API_KEY   Groq API 키 (없으면 하네스 비활성)
  SA_GROQ_MODEL     모델 id (기본: llama-3.3-70b-versatile)
  SA_GROQ_BASE_URL  엔드포인트 (기본: https://api.groq.com/openai/v1)
"""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request

log = logging.getLogger(__name__)

_DEFAULT_BASE = "https://api.groq.com/openai/v1"
_DEFAULT_MODEL = "llama-3.3-70b-versatile"
_TIMEOUT = 40


def groq_available() -> bool:
    """키가 설정돼 있으면 True. 하네스 활성 조건 점검용."""
    return bool(os.environ.get("SA_GROQ_API_KEY"))


class GroqClient:
    """Groq Chat Completions 호출 래퍼. 실패 시 None 반환(예외 삼킴)."""

    def __init__(self, api_key: str | None = None, model: str | None = None,
                 base_url: str | None = None):
        self.api_key = api_key or os.environ.get("SA_GROQ_API_KEY", "")
        self.model = model or os.environ.get("SA_GROQ_MODEL", _DEFAULT_MODEL)
        self.base_url = (base_url or os.environ.get("SA_GROQ_BASE_URL")
                         or _DEFAULT_BASE).rstrip("/")

    def chat(self, system: str, user: str, *, json_mode: bool = True,
             max_tokens: int = 700, temperature: float = 0.4) -> str | None:
        """1회 추론. 모델의 응답 텍스트를 돌려준다(실패 시 None)."""
        if not self.api_key:
            return None
        body: dict = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(body).encode(),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
                data = json.loads(resp.read())
            return data["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode()[:200]
            except Exception:
                pass
            log.warning("groq: HTTP %s — %s", e.code, detail)
            return None
        except Exception as exc:
            log.warning("groq: 호출 실패 — %s", exc)
            return None

    def chat_json(self, system: str, user: str, **kw) -> dict | None:
        """chat() 결과에서 JSON 객체를 파싱해 dict 로 돌려준다(실패 시 None)."""
        text = self.chat(system, user, json_mode=True, **kw)
        if not text:
            return None
        try:
            return json.loads(text)
        except Exception:
            # 모델이 앞뒤로 잡설을 붙였을 때 중괄호 범위만 떼어 재시도
            start, end = text.find("{"), text.rfind("}")
            if start >= 0 and end > start:
                try:
                    return json.loads(text[start:end + 1])
                except Exception:
                    return None
            return None

    def selftest(self) -> str:
        """키·모델·연결 상태를 한 줄로 진단(비밀 노출 없음)."""
        if not self.api_key:
            return ("groq 진단: SA_GROQ_API_KEY 미설정 → 하네스 비활성. "
                    "Render Environment 에 키를 추가하세요.")
        out = self.chat("You reply with JSON only.",
                        'Reply exactly {"ok": true}', max_tokens=20)
        if out is None:
            return (f"groq 진단: 호출 실패 model={self.model} "
                    "(키 무효/만료 또는 네트워크 확인 필요)")
        return f"groq 진단: ✅ 연결 OK model={self.model}"
