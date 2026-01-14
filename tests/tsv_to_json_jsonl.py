import csv
import json
import argparse
from pathlib import Path


def read_tsv(path: Path):
    """Read TSV with columns: key, source, translation, note."""
    rows = []
    with path.open("r", encoding="utf-8", newline="") as f:
        r = csv.reader(f, delimiter="\t")

        first = True
        for line in r:
            if not line:
                continue

            # Skip header row if present
            if first and line[0].lower() == "key":
                first = False
                continue
            first = False

            key = line[0] if len(line) > 0 else ""
            source = line[1] if len(line) > 1 else ""
            translation = line[2] if len(line) > 2 else ""
            note = line[3] if len(line) > 3 else ""

            rows.append(
                {
                    "key": key,
                    "source": source,
                    "translation": translation,
                    "note": note,
                }
            )
    return rows


def write_json(rows, out_path: Path, pretty: bool = False):
    """Write list of dicts as JSON array."""
    with out_path.open("w", encoding="utf-8") as f:
        indent = 2 if pretty else None
        json.dump(rows, f, ensure_ascii=False, indent=indent)


def write_jsonl(rows, out_path: Path):
    """Write list of dicts as JSON Lines (one JSON object per line)."""
    with out_path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Convert TSV (key, source, translation, note) into JSON or JSONL. "
            "Output format is chosen by the file extension: .json or .jsonl."
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
        help="Path to output file (.json or .jsonl).",
    )

    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON with indentation (only affects .json output).",
    )

    parser.add_argument(
        "--version",
        action="version",
        version="tsv_to_json_jsonl 1.0",
    )

    args = parser.parse_args()

    inp = Path(args.inp)
    out = Path(args.out)

    if not inp.is_file():
        parser.error(f"Input file does not exist: {inp}")

    rows = read_tsv(inp)

    suffix = out.suffix.lower()
    if suffix == ".json":
        write_json(rows, out, pretty=args.pretty)
        print(f"Wrote JSON to: {out}")
    elif suffix == ".jsonl":
        write_jsonl(rows, out)
        print(f"Wrote JSONL to: {out}")
    else:
        parser.error("Unsupported output format. Use file with .json or .jsonl extension.")


if __name__ == "__main__":
    main()
