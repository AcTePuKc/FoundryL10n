from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseProvider(ABC):
    @abstractmethod
    def auth_login(self, credentials: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def fetch_projects(self, token: str) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def fetch_segments(
        self,
        token: str,
        *,
        project_id: str | None = None,
        page: int | None = None,
    ) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def submit_suggestion(
        self,
        token: str,
        *,
        segment_id: str,
        suggestion_text: str,
    ) -> dict[str, Any]:
        raise NotImplementedError
