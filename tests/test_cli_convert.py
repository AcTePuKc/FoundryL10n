import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

pytest.importorskip("sqlmodel")

import main


def test_cli_convert_orders_by_key_and_preserves_fields(tmp_path: Path) -> None:
    runner = CliRunner()
    input_path = tmp_path / "segments.json"
    output_path = tmp_path / "segments.jsonl"

    payload = [
        {"key": "b", "source": "Second", "translation": "", "note": ""},
        {"key": "a", "source": "First", "translation": "Uno"},
    ]
    input_path.write_text(json.dumps(payload), encoding="utf-8")

    result = runner.invoke(
        main.app,
        ["convert", str(input_path), "--out", str(output_path)],
    )

    assert result.exit_code == 0
    lines = output_path.read_text(encoding="utf-8").splitlines()
    parsed = [json.loads(line) for line in lines if line.strip()]
    assert [row["key"] for row in parsed] == ["a", "b"]
    assert parsed[0]["note"] == ""
    assert parsed[1]["translation"] == ""
