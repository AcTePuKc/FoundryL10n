from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from core.rlm_segmenter import Segment
from core.tag_utils import extract_tags


_PLACEHOLDER_PATTERNS = (
    re.compile(r"<TSMARKER_\d+>"),
    re.compile(r"%[^\s]*[dsf]"),
    re.compile(r"\{\d+\}"),
    re.compile(r"\[BTN_[^\]]+\]"),
)


@dataclass(frozen=True)
class ValidationResult:
    is_valid: bool
    mismatches: list[dict[str, Any]]
    risk_flags: list[str]


def _matches_placeholder(tag: str) -> bool:
    return any(pattern.fullmatch(tag) for pattern in _PLACEHOLDER_PATTERNS)


def _extract_placeholders(tags: list[str]) -> list[str]:
    return [tag for tag in tags if _matches_placeholder(tag)]


def _compare_placeholder_sequences(
    source_tags: list[str],
    target_tags: list[str],
    mismatches: list[dict[str, Any]],
    risk_flags: list[str],
) -> None:
    source_placeholders = _extract_placeholders(source_tags)
    target_placeholders = _extract_placeholders(target_tags)
    if source_placeholders == target_placeholders:
        return

    min_len = min(len(source_placeholders), len(target_placeholders))
    for idx in range(min_len):
        if source_placeholders[idx] != target_placeholders[idx]:
            mismatches.append(
                {
                    "index": idx,
                    "expected": source_placeholders[idx],
                    "actual": target_placeholders[idx],
                    "category": "placeholder",
                }
            )
            risk_flags.append("placeholder_reordered")
    if len(source_placeholders) > len(target_placeholders):
        risk_flags.append("placeholder_missing")
    elif len(source_placeholders) < len(target_placeholders):
        risk_flags.append("placeholder_extra")


def validate_placeholder_order(
    source_text: str,
    target_text: str,
    context: dict[str, Any] | None = None,
) -> ValidationResult:
    del context
    mismatches: list[dict[str, Any]] = []
    risk_flags: list[str] = []
    source_tags = extract_tags(source_text or "")
    target_tags = extract_tags(target_text or "")
    _compare_placeholder_sequences(source_tags, target_tags, mismatches, risk_flags)
    return ValidationResult(not risk_flags, mismatches, sorted(set(risk_flags)))


def validate_segments(
    source_segments: list[Segment],
    target_segments: list[Segment],
    source_tags: list[str],
    target_tags: list[str],
    context: dict[str, Any] | None = None,
) -> ValidationResult:
    del context
    mismatches: list[dict[str, Any]] = []
    risk_flags: list[str] = []

    if source_tags != target_tags:
        min_len = min(len(source_tags), len(target_tags))
        for idx in range(min_len):
            if source_tags[idx] != target_tags[idx]:
                mismatches.append(
                    {
                        "index": idx,
                        "expected": source_tags[idx],
                        "actual": target_tags[idx],
                    }
                )
                risk_flags.append("reordered_tags")
        if len(source_tags) > len(target_tags):
            risk_flags.append("missing_tag")
        elif len(source_tags) < len(target_tags):
            risk_flags.append("extra_tag")

    source_kind_sequence = [seg.kind for seg in source_segments]
    target_kind_sequence = [seg.kind for seg in target_segments]
    if source_kind_sequence != target_kind_sequence:
        risk_flags.append("segment_boundary_mismatch")

    _compare_placeholder_sequences(source_tags, target_tags, mismatches, risk_flags)

    is_valid = not risk_flags
    return ValidationResult(is_valid, mismatches, sorted(set(risk_flags)))
