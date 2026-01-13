from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Callable
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from core.providers.base import BaseProvider

DEFAULT_MAPPING = {
    "source_text": "source",
    "target_text": "current_translation",
    "segment_id": "segment_id",
}
SUGGESTION_BLOCKLIST = ("approve", "publish", "accept", "overwrite", "finalize")


@dataclass(frozen=True)
class ProviderConfig:
    metadata: dict[str, Any]
    auth: dict[str, Any]
    endpoints: dict[str, Any]
    mapping: dict[str, Any]

    @classmethod
    def from_plugin(cls, plugin: dict[str, Any]) -> "ProviderConfig":
        return cls(
            metadata=plugin.get("metadata", {}),
            auth=plugin.get("auth", {}),
            endpoints=plugin.get("endpoints", {}),
            mapping=plugin.get("mapping", {}),
        )


class ProviderHttpClient(BaseProvider):
    def __init__(
        self,
        plugin: dict[str, Any],
        requester: Callable[[str, str, dict[str, str] | None, dict[str, Any] | None], Any]
        | None = None,
    ) -> None:
        self.config = ProviderConfig.from_plugin(plugin)
        self._requester = requester or self._default_request

    def auth_login(self, credentials: dict[str, Any]) -> dict[str, Any]:
        endpoint = self.config.auth.get("login_endpoint")
        if not endpoint:
            raise ValueError("Provider auth login endpoint is missing.")
        url = self.format_endpoint(endpoint)
        response = self._requester("POST", url, None, credentials)
        token_path = self.config.auth.get("token_path")
        token = self._extract_by_path(response, token_path) if token_path else None
        if token is None and isinstance(response, dict):
            token = response.get("token")
        if token is None:
            raise ValueError("Provider login did not return a token.")
        return {"token": token, "response": response}

    def fetch_projects(self, token: str) -> list[dict[str, Any]]:
        endpoint = self.config.endpoints.get("fetch_projects")
        if not endpoint:
            return []
        url = self.format_endpoint(endpoint)
        response = self._requester("GET", url, self._auth_headers(token), None)
        if isinstance(response, list):
            return response
        if isinstance(response, dict):
            for key in ("projects", "data", "items"):
                value = response.get(key)
                if isinstance(value, list):
                    return value
        return []

    def fetch_segments(
        self,
        token: str,
        *,
        project_id: str | None = None,
        page: int | None = None,
    ) -> list[dict[str, Any]]:
        endpoint = self.config.endpoints.get("fetch_segments")
        if not endpoint:
            raise ValueError("Provider fetch_segments endpoint is missing.")
        format_params: dict[str, str] = {"page": str(page or 1)}
        if project_id:
            format_params["project_id"] = project_id

        try:
            url = self.format_endpoint(endpoint, **format_params)
        except KeyError as e:
            raise ValueError(f"Endpoint requires parameter {e!r}, but it was not provided.") from e
        response = self._requester("GET", url, self._auth_headers(token), None)
        items = self._segment_items(response)
        mapping = {**DEFAULT_MAPPING, **self.config.mapping}
        segments: list[dict[str, Any]] = []
        for item in items:
            segment_id = self._extract_by_path(item, mapping["segment_id"])
            source = self._extract_by_path(item, mapping["source_text"])
            target = self._extract_by_path(item, mapping["target_text"])
            segments.append(
                {
                    "segment_id": segment_id,
                    "source": source,
                    "target": target,
                    "local_draft": "",
                }
            )
        return segments

    def submit_suggestion(
        self,
        token: str,
        *,
        segment_id: str,
        suggestion_text: str,
    ) -> dict[str, Any]:
        endpoint = self.config.endpoints.get("submit_suggestion")
        if not endpoint:
            raise ValueError("Provider submit_suggestion endpoint is missing.")
        if any(term in endpoint.lower() for term in SUGGESTION_BLOCKLIST):
            raise ValueError("submit_suggestion endpoint violates suggestions-only policy.")
        url = self.format_endpoint(endpoint, segment_id=segment_id)
        payload = {"segment_id": segment_id, "suggestion_text": suggestion_text}
        response = self._requester("POST", url, self._auth_headers(token), payload)
        return {"ok": True, "response": response}

    def format_endpoint(self, endpoint: str, **params: Any) -> str:
        expanded = endpoint.format(**params) if params else endpoint
        if urlparse(expanded).scheme:
            return expanded
        base_url = self.config.metadata.get("base_url", "").rstrip("/") + "/"
        return urljoin(base_url, expanded.lstrip("/"))

    def _auth_headers(self, token: str) -> dict[str, str]:
        auth_type = str(self.config.auth.get("type", "bearer")).lower()
        if auth_type in {"bearer", "oauth2"}:
            return {"Authorization": f"Bearer {token}"}
        elif auth_type == "basic":
            return {"Authorization": f"Basic {token}"}
        else:
            raise ValueError(f"Unsupported auth type: '{auth_type}'")

    def _segment_items(self, response: Any) -> list[dict[str, Any]]:
        if isinstance(response, list):
            return response
        if isinstance(response, dict):
            for key in ("segments", "data", "items"):
                value = response.get(key)
                if isinstance(value, list):
                    return value
        return []

    def _extract_by_path(self, payload: Any, path: str | None) -> Any:
        if path is None:
            return None
        current: Any = payload
        for part in path.split("."):
            if isinstance(current, dict):
                if part not in current:
                    return None
                current = current[part]
                continue
            if isinstance(current, list):
                if part.isdigit():
                    index = int(part)
                    if index >= len(current):
                        return None
                    current = current[index]
                    continue
                return None
            return None
        return current

    def _default_request(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None,
        json_body: dict[str, Any] | None,
    ) -> Any:
        data = None
        if json_body is not None:
            data = json.dumps(json_body).encode("utf-8")
        request = Request(url, data=data, method=method)
        for key, value in (headers or {}).items():
            request.add_header(key, value)
        if json_body is not None:
            request.add_header("Content-Type", "application/json")
        with urlopen(request, timeout=10) as response:
            raw = response.read().decode("utf-8")
        if not raw:
            return {}
        return json.loads(raw)
