from __future__ import annotations

import json
from pathlib import Path

import pytest

try:
    from jsonschema import Draft7Validator
    from services import plugin_validator
except ModuleNotFoundError:
    pytest.skip(
        "schema validator not available; skipping generic provider validation",
        allow_module_level=True,
    )


def test_generic_example_matches_schema() -> None:
    schema = plugin_validator.load_schema()
    validator = Draft7Validator(schema)
    example_path = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "plugins"
        / "generic_example.json"
    )

    errors = plugin_validator.validate_plugin(example_path, validator)

    assert errors == []


def test_generic_example_required_endpoints_present() -> None:
    example_path = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "plugins"
        / "generic_example.json"
    )
    data = json.loads(example_path.read_text(encoding="utf-8"))
    endpoints = data["endpoints"]
    required = ("base_url", "fetch_segments", "submit_suggestion")

    for key in required:
        assert key in endpoints

    for key in ("fetch_segments", "submit_suggestion"):
        endpoint = endpoints[key]
        if isinstance(endpoint, dict):
            assert endpoint.get("method")
            assert endpoint.get("path")
