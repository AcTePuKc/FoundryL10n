from __future__ import annotations

from typing import Any

import pytest

provider_module = pytest.importorskip("services.provider_http_client")
ProviderHttpClient = provider_module.ProviderHttpClient


def build_plugin(**overrides: Any) -> dict[str, Any]:
    plugin = {
        "metadata": {"name": "Demo", "id": "demo", "base_url": "https://example.com/api"},
        "auth": {"type": "bearer", "login_endpoint": "/auth/login"},
        "endpoints": {
            "fetch_projects": "/projects",
            "fetch_segments": "/projects/{project_id}/segments?page={page}",
            "submit_suggestion": "/segments/{segment_id}/suggestions",
        },
        "mapping": {
            "source_text": "payload.source",
            "target_text": "payload.target",
            "segment_id": "id",
        },
    }
    plugin.update(overrides)
    return plugin


def test_format_endpoint_with_placeholders() -> None:
    client = ProviderHttpClient(build_plugin())
    url = client.format_endpoint(
        "/projects/{project_id}/segments?page={page}",
        project_id="alpha",
        page=2,
    )
    assert url == "https://example.com/api/projects/alpha/segments?page=2"


def test_mapping_extraction_for_segments() -> None:
    captured: dict[str, Any] = {}

    def stub_request(
        method: str,
        url: str,
        headers: dict[str, str] | None,
        json_body: dict[str, Any] | None,
    ) -> Any:
        captured["method"] = method
        captured["url"] = url
        captured["headers"] = headers
        captured["json_body"] = json_body
        return {
            "segments": [
                {
                    "id": "seg-1",
                    "payload": {"source": "Hello", "target": "Salut"},
                }
            ]
        }

    client = ProviderHttpClient(build_plugin(), requester=stub_request)
    segments = client.fetch_segments("token-123", project_id="alpha", page=1)

    assert captured["method"] == "GET"
    assert "projects/alpha/segments?page=1" in captured["url"]
    assert segments == [
        {
            "segment_id": "seg-1",
            "source": "Hello",
            "target": "Salut",
            "local_draft": "",
        }
    ]


def test_suggestions_only_guardrails() -> None:
    plugin = build_plugin(
        endpoints={
            "fetch_segments": "/segments",
            "submit_suggestion": "/segments/{segment_id}/publish",
        }
    )
    client = ProviderHttpClient(plugin)

    with pytest.raises(ValueError, match="suggestions-only"):
        client.submit_suggestion("token-123", segment_id="seg-1", suggestion_text="Hi")
