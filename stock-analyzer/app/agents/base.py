"""모든 에이전트의 공통 베이스."""
from __future__ import annotations

from abc import ABC


class Agent(ABC):
    name: str = "agent"
    role: str = "generic"
    description: str = ""

    def info(self) -> dict:
        return {"name": self.name, "role": self.role, "description": self.description}
