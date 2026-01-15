import csv
import json
from pathlib import Path

from tests import tsv_to_json_jsonl as converters


def test_json_array_to_jsonl_orders_by_key_and_preserves_fields(tmp_path: Path) -> None:
    input_path = tmp_path / "input.json"
    output_path = tmp_path / "output.jsonl"

    rows = [
        {"key": "b", "source": "Second", "translation": "", "note": ""},
        {"key": "a", "source": "First", "translation": "Uno", "note": "keep"},
    ]
    input_path.write_text(json.dumps(rows), encoding="utf-8")

    converted = converters.read_rows(input_path)
    converters.write_rows(converted, output_path)

    lines = output_path.read_text(encoding="utf-8").splitlines()
    parsed = [json.loads(line) for line in lines if line.strip()]

    assert [row["key"] for row in parsed] == ["a", "b"]
    assert parsed[1]["translation"] == ""
    assert parsed[1]["note"] == ""


def test_jsonl_to_tsv_includes_note_and_translation_columns(tmp_path: Path) -> None:
    input_path = tmp_path / "input.jsonl"
    output_path = tmp_path / "output.tsv"

    input_path.write_text(
        "\n".join(
            [
                json.dumps({"key": "seg-1", "source": "Hello", "translation": ""}),
                json.dumps({"key": "seg-2", "source": "World", "note": ""}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    converted = converters.read_rows(input_path)
    converters.write_rows(converted, output_path)

    with output_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        rows = list(reader)

    assert reader.fieldnames is not None
    assert "note" in reader.fieldnames
    assert "translation" in reader.fieldnames
    assert rows[0]["translation"] == ""
    assert rows[1]["note"] == ""
