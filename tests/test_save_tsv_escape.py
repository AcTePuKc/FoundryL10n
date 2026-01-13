import csv
from pathlib import Path

from core.parser import FoundryParser, TranslationSegment


def test_save_tsv_escapes_tabs_newlines_and_quotes(tmp_path: Path) -> None:
    parser = FoundryParser()
    parser.headers = ["key", "source", "translation"]
    parser.text_col = "source"
    parser.target_col = "translation"

    segments = [
        TranslationSegment(
            key="seg-1",
            source_text="Source",
            translation='Line1\nLine\t"quoted"',
            original_row={
                "key": "seg-1",
                "source": "Source",
                "translation": "",
            },
        )
    ]

    output_path = tmp_path / "export.tsv"
    parser.save_tsv(segments, output_path)

    with output_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(
            handle,
            delimiter="\t",
            quoting=csv.QUOTE_NONE,
            escapechar="\\",
        )
        rows = list(reader)

    assert rows[0] == ["key", "source", "translation"]
    assert rows[1] == ["seg-1", "Source", 'Line1\nLine\t"quoted"']
