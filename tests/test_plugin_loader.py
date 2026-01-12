from __future__ import annotations

import json
from pathlib import Path

import pytest

try:
    import jsonschema  # noqa: F401
except ModuleNotFoundError:
    pytest.skip(
        "jsonschema not installed; skipping plugin loader tests",
        allow_module_level=True,
    )

from services.plugin_loader import PluginLoader


def write_schema(path: Path) -> None:
    schema = {
        "type": "object",
        "properties": {
            "metadata": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "id": {"type": "string"},
                    "base_url": {"type": "string"},
                },
                "required": ["name", "id", "base_url"],
            },
            "auth": {
                "type": "object",
                "properties": {
                    "type": {"enum": ["bearer", "basic", "oauth2"]},
                    "login_endpoint": {"type": "string"},
                },
                "required": ["type", "login_endpoint"],
            },
            "endpoints": {
                "type": "object",
                "properties": {
                    "fetch_segments": {"type": "string"},
                    "submit_suggestion": {"type": "string"},
                },
                "required": ["fetch_segments", "submit_suggestion"],
            },
        },
        "required": ["metadata", "auth", "endpoints"],
    }
    path.write_text(json.dumps(schema), encoding="utf-8")


def write_plugin(path: Path, *, metadata_id: str, name: str = "Provider") -> None:
    plugin = {
        "metadata": {
            "name": name,
            "id": metadata_id,
            "base_url": "https://example.com",
        },
        "auth": {"type": "basic", "login_endpoint": "/login"},
        "endpoints": {
            "fetch_segments": "/segments",
            "submit_suggestion": "/submit",
        },
    }
    path.write_text(json.dumps(plugin), encoding="utf-8")


def test_valid_plugin_discovery(tmp_path: Path) -> None:
    plugin_dir = tmp_path / "plugins"
    plugin_dir.mkdir()
    schema_path = tmp_path / "schema.json"
    write_schema(schema_path)
    write_plugin(plugin_dir / "alpha.json", metadata_id="alpha")

    registry = PluginLoader(plugin_dir=plugin_dir, schema_path=schema_path).load_registry()

    assert registry.providers["alpha"]["metadata"]["id"] == "alpha"
    assert registry.entries[0].is_valid
    assert not registry.warnings


def test_invalid_json_handling(tmp_path: Path) -> None:
    plugin_dir = tmp_path / "plugins"
    plugin_dir.mkdir()
    schema_path = tmp_path / "schema.json"
    write_schema(schema_path)
    (plugin_dir / "broken.json").write_text("{not-json", encoding="utf-8")

    registry = PluginLoader(plugin_dir=plugin_dir, schema_path=schema_path).load_registry()

    assert registry.entries[0].data is None
    assert any("Invalid JSON" in warning for warning in registry.warnings)


def test_duplicate_provider_ids(tmp_path: Path) -> None:
    plugin_dir = tmp_path / "plugins"
    plugin_dir.mkdir()
    schema_path = tmp_path / "schema.json"
    write_schema(schema_path)
    write_plugin(plugin_dir / "alpha.json", metadata_id="dup")
    write_plugin(plugin_dir / "beta.json", metadata_id="dup")

    registry = PluginLoader(plugin_dir=plugin_dir, schema_path=schema_path).load_registry()

    assert set(registry.providers) == {"dup"}
    assert len(registry.entries) == 2
    assert any("duplicates another plugin" in warning for warning in registry.warnings)


def test_deterministic_ordering(tmp_path: Path) -> None:
    plugin_dir = tmp_path / "plugins"
    plugin_dir.mkdir()
    schema_path = tmp_path / "schema.json"
    write_schema(schema_path)
    write_plugin(plugin_dir / "zeta.json", metadata_id="zeta")
    write_plugin(plugin_dir / "alpha.json", metadata_id="alpha")

    registry = PluginLoader(plugin_dir=plugin_dir, schema_path=schema_path).load_registry()

    paths = [entry.path.name for entry in registry.entries]
    assert paths == ["alpha.json", "zeta.json"]
