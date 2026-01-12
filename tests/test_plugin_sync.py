from __future__ import annotations

import json
from pathlib import Path

import pytest

try:
    import urllib.request  # noqa: F401
except ModuleNotFoundError:
    pytest.skip(
        "urllib.request not available; skipping plugin sync tests",
        allow_module_level=True,
    )

from services.plugin_sync_service import (
    GitHubPluginSyncService,
    GitHubRepoConfig,
)


class FakeRequester:
    def __init__(self, responses: dict[str, bytes]) -> None:
        self.responses = responses
        self.calls: list[str] = []

    def __call__(self, url: str) -> bytes:
        self.calls.append(url)
        return self.responses[url]


def test_url_building() -> None:
    repo = GitHubRepoConfig(
        owner="octo",
        repo="providers",
        branch="dev",
        plugins_path="plugins",
    )
    service = GitHubPluginSyncService(repo=repo)

    assert (
        service.build_manifest_url()
        == "https://api.github.com/repos/octo/providers/contents/plugins?ref=dev"
    )
    assert (
        service.build_raw_url("plugins/alpha.json")
        == "https://raw.githubusercontent.com/octo/providers/dev/plugins/alpha.json"
    )


def test_downloads_manifest_entries(tmp_path: Path) -> None:
    repo = GitHubRepoConfig(
        owner="octo",
        repo="providers",
        branch="main",
        plugins_path="plugins",
    )
    service = GitHubPluginSyncService(repo=repo, plugin_dir=tmp_path)
    manifest_url = service.build_manifest_url()
    raw_beta = service.build_raw_url("plugins/beta.json")
    responses = {
        manifest_url: json.dumps(
            [
                {
                    "name": "alpha.json",
                    "path": "plugins/alpha.json",
                    "download_url": "https://cdn.example.com/alpha.json",
                },
                {
                    "name": "schema.json",
                    "path": "plugins/schema.json",
                    "download_url": "https://cdn.example.com/schema.json",
                },
                {
                    "name": "beta.json",
                    "path": "plugins/beta.json",
                    "download_url": None,
                },
                {"name": "notes.txt", "path": "plugins/notes.txt"},
            ]
        ).encode("utf-8"),
        "https://cdn.example.com/alpha.json": b"{\"alpha\": true}",
        raw_beta: b"{\"beta\": true}",
    }
    service._requester = FakeRequester(responses)

    result = service.sync_plugins()

    assert (tmp_path / "alpha.json").read_text(encoding="utf-8") == "{\"alpha\": true}"
    assert (tmp_path / "beta.json").read_text(encoding="utf-8") == "{\"beta\": true}"
    assert result.downloaded == (tmp_path / "alpha.json", tmp_path / "beta.json")
    assert not result.conflicts
    assert not result.errors


def test_safe_overwrite_rules(tmp_path: Path) -> None:
    repo = GitHubRepoConfig(
        owner="octo",
        repo="providers",
        branch="main",
        plugins_path="plugins",
    )
    service = GitHubPluginSyncService(repo=repo, plugin_dir=tmp_path)
    manifest_url = service.build_manifest_url()
    remote_url = "https://cdn.example.com/alpha.json"
    (tmp_path / "alpha.json").write_text("{\"alpha\": false}", encoding="utf-8")
    responses = {
        manifest_url: json.dumps(
            [
                {
                    "name": "alpha.json",
                    "path": "plugins/alpha.json",
                    "download_url": remote_url,
                }
            ]
        ).encode("utf-8"),
        remote_url: b"{\"alpha\": true}",
    }
    service._requester = FakeRequester(responses)

    result = service.sync_plugins()

    assert (tmp_path / "alpha.json").read_text(encoding="utf-8") == "{\"alpha\": false}"
    assert result.conflicts == (tmp_path / "alpha.json",)

    allow_overwrite = service.sync_plugins(allow_overwrite=True)

    assert (tmp_path / "alpha.json").read_text(encoding="utf-8") == "{\"alpha\": true}"
    assert allow_overwrite.updated == (tmp_path / "alpha.json",)
