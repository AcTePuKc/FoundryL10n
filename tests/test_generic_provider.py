from __future__ import annotations

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
