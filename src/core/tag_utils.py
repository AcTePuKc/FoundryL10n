import re
from typing import Pattern

_TAG_PATTERN = (
    r"@@\s*PLACEHOLDER_\d+\s*@@"
    r"|<[^>]+>"
    r"|\[[^\]]+\]"
    r"|\{[^\}]+\}"
    r"|%.*?[dsf]"
)
_TAG_REGEX: Pattern[str] = re.compile(_TAG_PATTERN)


def tag_regex() -> Pattern[str]:
    return _TAG_REGEX


def extract_tags(text: str) -> list[str]:
    if not text:
        return []
    return [match.group(0) for match in _TAG_REGEX.finditer(text)]


def strip_tags(text: str) -> str:
    if not text:
        return ""
    return _TAG_REGEX.sub("", text)
