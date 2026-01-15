import argparse
import csv
import json
from pathlib import Path
from typing import Iterable, List, Dict, Any


DEFAULT_FIELDS = ["key", "source", "translation", "note"]


def _normalize_row(row: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(row)
    if normalized.get("translation") is None:
        normalized["translation"] = ""
    if normalized.get("note") is None:
        normalized["note"] = ""
    for field in DEFAULT_FIELDS:
        normalized.setdefault(field, "")
    return normalized


def _order_rows(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    ordered = [_normalize_row(row) for row in rows]
    if ordered and all(str(row.get("key", "")) for row in ordered):
        indexed = list(enumerate(ordered))
        indexed.sort(key=lambda item: (str(item[1].get("key", "")), item[0]))
        return [row for _, row in indexed]
    return ordered


def _fieldnames(rows: List[Dict[str, Any]]) -> List[str]:
    fields = [field for field in DEFAULT_FIELDS if any(field in row for row in rows)]
    extras = sorted({key for row in rows for key in row.keys() if key not in fields})
    return fields + extras


def read_tsv(path: Path) -> List[Dict[str, Any]]:
    """Read TSV rows, keeping key/source/translation/note."""
    rows = []
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        if reader.fieldnames is None:
            return []
        for row in reader:
            rows.append(_normalize_row(row))
    return _order_rows(rows)


def read_json(path: Path) -> List[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    rows = data.get("segments") if isinstance(data, dict) else data
    if not isinstance(rows, list):
        raise ValueError("JSON input must be a list or object with 'segments'.")
    return _order_rows([row for row in rows if isinstance(row, dict)])


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped:
                continue
            rows.append(json.loads(stripped))
    return _order_rows([row for row in rows if isinstance(row, dict)])


def write_json(rows: List[Dict[str, Any]], out_path: Path, pretty: bool = False):
    """Write list of dicts as JSON array."""
    with out_path.open("w", encoding="utf-8") as f:
        indent = 2 if pretty else None
        json.dump(rows, f, ensure_ascii=False, indent=indent)


def write_jsonl(rows: List[Dict[str, Any]], out_path: Path):
    """Write list of dicts as JSON Lines (one JSON object per line)."""
    with out_path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def write_tsv(rows: List[Dict[str, Any]], out_path: Path) -> None:
    fieldnames = _fieldnames(rows)
    with out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def read_rows(path: Path) -> List[Dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".tsv":
        return read_tsv(path)
    if suffix == ".json":
        return read_json(path)
    if suffix == ".jsonl":
        return read_jsonl(path)
    raise ValueError("Unsupported input format. Use .tsv, .json, or .jsonl.")


def write_rows(rows: List[Dict[str, Any]], out_path: Path, pretty: bool = False) -> None:
    suffix = out_path.suffix.lower()
    if suffix == ".tsv":
        write_tsv(rows, out_path)
        return
    if suffix == ".json":
        write_json(rows, out_path, pretty=pretty)
        return
    if suffix == ".jsonl":
        write_jsonl(rows, out_path)
        return
    raise ValueError("Unsupported output format. Use .tsv, .json, or .jsonl.")


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
