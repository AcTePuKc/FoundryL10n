from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from jsonschema import Draft7Validator

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "plugins" / "schema.json"


def load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def iter_plugin_files(target: Path) -> list[Path]:
    if target.is_dir():
        return sorted(
            file
            for file in target.rglob("*.json")
            if file.name != SCHEMA_PATH.name
        )
    return [target]


def format_error_path(error: Exception, fallback: str) -> str:
    if not hasattr(error, "path"):
        return fallback
    path = ".".join(str(part) for part in getattr(error, "path"))
    return path or fallback


def validate_plugin(path: Path, validator: Draft7Validator) -> list[str]:
    errors: list[str] = []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(
            f"{path}: Invalid JSON - {exc.msg} (line {exc.lineno}, column {exc.colno})"
        )
        return errors
    except OSError as exc:
        errors.append(f"{path}: Unable to read file - {exc}")
        return errors

    for error in sorted(validator.iter_errors(data), key=lambda item: list(item.path)):
        location = format_error_path(error, "(root)")
        errors.append(f"{path}: {location}: {error.message}")
    return errors


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate provider plugin JSON files against the schema.",
    )
    parser.add_argument(
        "path",
        help="Path to a plugin JSON file or a directory containing plugins.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    target = Path(args.path)

    if not target.exists():
        print(f"Path not found: {target}")
        return 1

    try:
        schema = load_schema()
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Failed to load schema at {SCHEMA_PATH}: {exc}")
        return 1

    validator = Draft7Validator(schema)
    plugin_files = iter_plugin_files(target)
    if not plugin_files:
        print(f"No plugin JSON files found in {target}")
        return 1

    all_errors: list[str] = []
    for plugin_file in plugin_files:
        all_errors.extend(validate_plugin(plugin_file, validator))

    if all_errors:
        print("Validation errors found:")
        for error in all_errors:
            print(f"- {error}")
        return 1

    print(f"Validated {len(plugin_files)} plugin file(s) successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
