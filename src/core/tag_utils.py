import re
from typing import Pattern

_ORIGINAL_TAG_PATTERNS = (
    r"<[^>]+>"
    r"|\[[^\]]+\]"
    r"|\{[^\}]+\}"
    r"|%.*?[dsf]"
)
_ORIGINAL_TAG_REGEX: Pattern[str] = re.compile(_ORIGINAL_TAG_PATTERNS)
_PLACEHOLDER_PATTERN = r"@@\s*PLACEHOLDER_\d+\s*@@"
_TAG_PATTERN = f"{_PLACEHOLDER_PATTERN}|{_ORIGINAL_TAG_PATTERNS}"
_TAG_REGEX: Pattern[str] = re.compile(_TAG_PATTERN)


def tag_regex() -> Pattern[str]:
    return _TAG_REGEX


def original_tag_regex() -> Pattern[str]:
    return _ORIGINAL_TAG_REGEX


def extract_tags(text: str) -> list[str]:
    if not text:
        return []
    return [match.group(0) for match in _TAG_REGEX.finditer(text)]


def strip_tags(text: str) -> str:
    if not text:
        return ""
    return _TAG_REGEX.sub("", text)
