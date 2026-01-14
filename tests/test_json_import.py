import json
from pathlib import Path

from core.parser import FoundryParser


def test_parse_json_list_segments(tmp_path: Path) -> None:
    payload = [
        {
            "key": "seg-1",
            "source": "Hello",
            "translation": "Hola",
            "context": "Greeting",
            "custom_fields": {"tone": "formal"},
        },
        {
            "key": "seg-2",
            "source": "Bye",
        },
    ]
    input_path = tmp_path / "segments.json"
    input_path.write_text(json.dumps(payload), encoding="utf-8")

    parser = FoundryParser()
    segments = parser.parse_json(input_path)

    assert len(segments) == 2
    assert segments[0].key == "seg-1"
    assert segments[0].source_text == "Hello"
    assert segments[0].translation == "Hola"
    assert segments[0].context == "Greeting"
    assert segments[0].original_row["custom_fields"] == {"tone": "formal"}
    assert segments[1].key == "seg-2"
    assert segments[1].source_text == "Bye"


def test_parse_json_object_segments(tmp_path: Path) -> None:
    payload = {
        "segments": [
            {"key": "seg-3", "source": "Thanks", "translation": ""},
        ]
    }
    input_path = tmp_path / "segments.json"
    input_path.write_text(json.dumps(payload), encoding="utf-8")

    parser = FoundryParser()
    segments = parser.parse_path(input_path)

    assert len(segments) == 1
    assert segments[0].key == "seg-3"
    assert segments[0].source_text == "Thanks"
