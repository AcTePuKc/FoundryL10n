from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.rlm_segmenter import Segment


@dataclass(frozen=True)
class ValidationResult:
    is_valid: bool
    mismatches: list[dict[str, Any]]
    risk_flags: list[str]


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

    source_tag_sequence = _tag_sequence(source_segments)
    target_tag_sequence = _tag_sequence(target_segments)
    if source_tag_sequence != target_tag_sequence:
        risk_flags.append("segment_boundary_mismatch")

    is_valid = not risk_flags
    return ValidationResult(is_valid, mismatches, sorted(set(risk_flags)))


def _tag_sequence(segments: list[Segment]) -> list[str]:
    return [seg.value for seg in segments if seg.kind == "tag"]
