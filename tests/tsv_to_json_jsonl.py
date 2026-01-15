import argparse
import sys
from pathlib import Path
from typing import List, Dict, Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT / "src"))

from core.parser import FoundryParser


def read_rows(path: Path) -> List[Dict[str, Any]]:
    parser = FoundryParser()
    segments = parser.parse_path(path)
    rows = parser.build_export_rows(segments, include_empty_fields=True)
    return parser.order_rows_by_key(rows)


def write_rows(
    rows: List[Dict[str, Any]],
    out_path: Path,
    pretty: bool = False,
) -> None:
    parser = FoundryParser()
    parser.save_rows(rows, out_path, pretty=pretty)


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Convert TSV/JSON/JSONL files across formats. "
            "Output format is chosen by the file extension: .tsv, .json, or .jsonl."
        )
    )

    parser.add_argument(
        "--in",
        dest="inp",
        required=True,
        help="Path to input TSV file (UTF-8, tab-separated).",
    )

    parser.add_argument(
        "--out",
        dest="out",
        required=True,
        help="Path to output file (.tsv, .json, or .jsonl).",
    )

    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON with indentation (only affects .json output).",
    )

    parser.add_argument(
        "--version",
        action="version",
        version="tsv_to_json_jsonl 1.1",
    )

    args = parser.parse_args()

    inp = Path(args.inp)
    out = Path(args.out)

    if not inp.is_file():
        parser.error(f"Input file does not exist: {inp}")

    rows = read_rows(inp)
    write_rows(rows, out, pretty=args.pretty)
    print(f"Wrote {out.suffix.upper().lstrip('.')} to: {out}")


if __name__ == "__main__":
    main()
