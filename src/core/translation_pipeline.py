from __future__ import annotations

import os
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Iterator

from core.parser import TranslationSegment


@dataclass(frozen=True)
class JSONLPipelineEntry:
    order: int
    payload: dict

    def to_jsonl(self) -> str:
        return json.dumps(self.payload, ensure_ascii=False)


def segment_to_jsonl_entry(segment: TranslationSegment, order: int) -> JSONLPipelineEntry:
    payload: dict[str, object] = {
        "order": order,
        "key": segment.key,
        "source": segment.source_text,
    }

    if segment.translation:
        payload["translation"] = segment.translation
    if segment.context:
        payload["note"] = segment.context
    if segment.ai_draft:
        payload["ai_draft"] = segment.ai_draft
    if segment.provider_id:
        payload["provider_id"] = segment.provider_id
    if segment.remote_id:
        payload["remote_id"] = segment.remote_id
    if segment.last_sync:
        payload["last_sync"] = segment.last_sync

    custom_fields = segment.original_row.get("custom_fields")
    if custom_fields:
        payload["custom_fields"] = custom_fields

    return JSONLPipelineEntry(order=order, payload=payload)


def iter_jsonl_chunks(
    segments: Iterable[TranslationSegment],
    chunk_size: int,
) -> Iterator[list[JSONLPipelineEntry]]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be a positive integer")

    chunk: list[JSONLPipelineEntry] = []
    for index, segment in enumerate(segments):
        chunk.append(segment_to_jsonl_entry(segment, index))
        if len(chunk) >= chunk_size:
            yield chunk
            chunk = []
    if chunk:
        yield chunk


def load_translated_keys(jsonl_path: Path) -> set[str]:
    if not jsonl_path.exists():
        return set()

    translated: set[str] = set()
    with jsonl_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                entry = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            if not isinstance(entry, dict):
                continue
            key = entry.get("key")
            translation = entry.get("translation")
            if key and isinstance(translation, str) and translation.strip():
                translated.add(str(key))
    return translated


def append_jsonl_entries(output_path: Path, entries: Iterable[JSONLPipelineEntry]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("a", encoding="utf-8") as handle:
        for entry in entries:
            handle.write(entry.to_jsonl())
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())


def run_ordered_jsonl_pipeline(
    *,
    segments: Iterable[TranslationSegment],
    chunk_size: int,
    process_chunk: Callable[[list[JSONLPipelineEntry]], list[JSONLPipelineEntry]] | None = None,
    output_path: Path | None = None,
    resume_from: Path | None = None,
    single_thread: bool = True,
) -> Iterator[JSONLPipelineEntry]:
    if not single_thread:
        raise ValueError("Only single-thread mode is supported for now.")

    skip_keys = set()
    if resume_from is not None:
        skip_keys = load_translated_keys(resume_from)
    elif output_path is not None:
        skip_keys = load_translated_keys(output_path)

    for chunk in iter_jsonl_chunks(segments, chunk_size):
        filtered = [entry for entry in chunk if entry.payload.get("key") not in skip_keys]
        if not filtered:
            continue
        processed = process_chunk(filtered) if process_chunk else filtered
        order_by_key = {
            str(entry.payload.get("key")): entry.order for entry in filtered
        }
        normalized: list[JSONLPipelineEntry] = []
        for entry in processed:
            key = str(entry.payload.get("key"))
            expected_order = order_by_key.get(key, entry.order)
            if entry.order != expected_order:
                entry = JSONLPipelineEntry(order=expected_order, payload=entry.payload)
            normalized.append(entry)
        ordered = sorted(
            normalized,
            key=lambda entry: (entry.order, str(entry.payload.get("key") or "")),
        )
        if output_path is not None:
            append_jsonl_entries(output_path, ordered)
        for entry in ordered:
            yield entry
