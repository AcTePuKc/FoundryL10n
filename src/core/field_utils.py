from __future__ import annotations


def is_custom_field_missing(field_type: str, value: object) -> bool:
    if value is None:
        return True
    if field_type in {"text", "textarea", "select", "date"} and isinstance(value, str):
        return not value.strip()
    if field_type in {"number", "boolean"}:
        return False
    if isinstance(value, (list, dict, tuple, set)):
        return len(value) == 0
    return False
