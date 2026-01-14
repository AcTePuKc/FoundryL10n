from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.tag_utils import tag_regex


@dataclass(frozen=True)
class Segment:
    kind: str
    value: str


@dataclass(frozen=True)
class SegmentResult:
    segments: list[Segment]
    tags: list[str]
    risk_flags: list[str]


class RLMSegmenter:
    def __init__(self) -> None:
        self._tag_regex = tag_regex()

    def segment(
        self,
        raw_line: str,
        masked_line: str | None = None,
        context: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SegmentResult:
        del context, metadata
        line = masked_line if masked_line is not None else raw_line

        if not line:
            return SegmentResult([], [], [])

        risk_flags: list[str] = []
        if self._has_unbalanced_delimiters(line):
            return SegmentResult(
                [Segment(kind="text", value=line)],
                [],
                ["unbalanced_delimiters"],
            )

        segments: list[Segment] = []
        tags: list[str] = []
        last_idx = 0
        for match in self._tag_regex.finditer(line):
            start, end = match.span()
            if start > last_idx:
                segments.append(Segment(kind="text", value=line[last_idx:start]))
            value = match.group(0)
            segments.append(Segment(kind="tag", value=value))
            tags.append(value)
            last_idx = end
        if last_idx < len(line):
            segments.append(Segment(kind="text", value=line[last_idx:]))

        if not segments:
            return SegmentResult([Segment(kind="text", value=line)], [], ["segmenter_fallback"])

        return SegmentResult(segments, tags, risk_flags)

    @staticmethod
    def _has_unbalanced_delimiters(line: str) -> bool:
        return (
            line.count("<") != line.count(">")
            or line.count("[") != line.count("]")
            or line.count("{") != line.count("}")
        )
