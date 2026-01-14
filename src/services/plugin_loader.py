from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Iterable

from jsonschema import Draft7Validator

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "plugins" / "schema.json"
PLUGIN_DIR = SCHEMA_PATH.parent


@dataclass(frozen=True)
class PluginEntry:
    path: Path
    name: str
    metadata_id: str | None
    data: dict | None
    errors: tuple[str, ...]

    @property
    def is_valid(self) -> bool:
        return self.data is not None and self.metadata_id is not None and not self.errors


@dataclass(frozen=True)
class PluginRegistry:
    providers: dict[str, dict]
    entries: tuple[PluginEntry, ...]
    warnings: tuple[str, ...]


class PluginLoader:
    def __init__(self, plugin_dir: Path | None = None, schema_path: Path | None = None):
        self.plugin_dir = plugin_dir or PLUGIN_DIR
        self.schema_path = schema_path or SCHEMA_PATH

    def _load_schema(self) -> tuple[dict | None, str | None]:
        try:
            raw = self.schema_path.read_text(encoding="utf-8")
            return json.loads(raw), None
        except (OSError, json.JSONDecodeError) as exc:
            return None, str(exc)

    def _iter_plugin_files(self) -> Iterable[Path]:
        if not self.plugin_dir.exists():
            return []
        return sorted(
            file
            for file in self.plugin_dir.rglob("*.json")
            if file.name != self.schema_path.name
        )

    def _format_error_path(self, error: Exception, fallback: str) -> str:
        if not hasattr(error, "path"):
            return fallback
        path = ".".join(str(part) for part in getattr(error, "path"))
        return path or fallback

    def _load_plugin_json(self, path: Path) -> tuple[dict | None, list[str]]:
        try:
            return json.loads(path.read_text(encoding="utf-8")), []
        except json.JSONDecodeError as exc:
            return None, [
                f"{path}: Invalid JSON - {exc.msg} (line {exc.lineno}, column {exc.colno})"
            ]
        except OSError as exc:
            return None, [f"{path}: Unable to read file - {exc}"]

    def _validate_plugin(self, data: dict, validator: Draft7Validator, path: Path) -> list[str]:
        errors: list[str] = []
        for error in sorted(validator.iter_errors(data), key=lambda item: list(item.path)):
            location = self._format_error_path(error, "(root)")
            errors.append(f"{path}: {location}: {error.message}")
        return errors

    def _normalize_custom_fields(self, data: dict) -> list[dict]:
        raw_fields = data.get("custom_fields", [])
        if not isinstance(raw_fields, list):
            return []
        normalized: list[dict] = []
        for raw in raw_fields:
            if not isinstance(raw, dict):
                continue
            normalized.append(
                {
                    "id": raw.get("id"),
                    "label": raw.get("label"),
                    "type": raw.get("type"),
                    "required": bool(raw.get("required", False)),
                    "default": raw.get("default"),
                    "validation": validation
                    if isinstance((validation := raw.get("validation")), dict)
                    else {},
                }
            )
        return normalized

    def load_registry(self) -> PluginRegistry:
        warnings: list[str] = []
        providers: dict[str, dict] = {}
        entries: list[PluginEntry] = []

        schema, schema_error = self._load_schema()
        validator = Draft7Validator(schema) if schema else None
        if schema_error:
            warnings.append(f"Schema load failed: {schema_error}")

        plugin_files = list(self._iter_plugin_files())
        for plugin_file in plugin_files:
            data, errors = self._load_plugin_json(plugin_file)
            if data is not None and validator is not None:
                errors.extend(self._validate_plugin(data, validator, plugin_file))
            elif data is not None and validator is None:
                errors.append("Schema unavailable; skipping validation.")

            metadata = data.get("metadata", {}) if data else {}
            metadata_id = metadata.get("id") if isinstance(metadata, dict) else None
            name = metadata.get("name") if isinstance(metadata, dict) else None
            display_name = name or plugin_file.stem

            if not errors and metadata_id in providers:
                errors.append(
                    f"{plugin_file}: metadata.id '{metadata_id}' duplicates another plugin."
                )

            plugin_data = data if not errors else None
            if plugin_data is not None:
                plugin_data["custom_fields"] = self._normalize_custom_fields(plugin_data)

            entry = PluginEntry(
                path=plugin_file,
                name=display_name,
                metadata_id=metadata_id,
                data=plugin_data,
                errors=tuple(errors),
            )
            entries.append(entry)

            if entry.is_valid and entry.metadata_id is not None and entry.data is not None:
                providers[entry.metadata_id] = entry.data
            else:
                warnings.extend(entry.errors)

        return PluginRegistry(
            providers=providers,
            entries=tuple(entries),
            warnings=tuple(warnings),
        )
