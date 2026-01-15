import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from core.engine import TranslationEngine
from core.parser import FoundryParser, TranslationSegment
from core.translation_pipeline import (
    JSONLPipelineEntry,
    iter_segment_chunks,
    run_ordered_jsonl_pipeline,
)


class DummyLLM:
    def translate_segment(
        self,
        text: str,
        target_lang: str,
        project_name: str = "default",
        glossary: str = "",
        style: str = "",
        forbidden: str = "",
        temp: float = 0.1,
        prompt_template: str = "",
        current_translation: str = "",
        context_extra: str = "",
    ) -> tuple[str, str]:
        return f"[DUMMY {target_lang}] {text}", ""

    def repair_placeholders(
        self,
        source_line: str,
        candidate_translation: str,
        expected_placeholders: list[str],
    ) -> tuple[str | None, str]:
        return candidate_translation, ""


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the CLI translation pipeline using a dummy LLM for local testing."
        )
    )
    parser.add_argument("--input", dest="input_path", required=True)
    parser.add_argument("--in-format", dest="input_format", choices=["tsv", "json", "jsonl"])
    parser.add_argument("--output", dest="output_path", required=True)
    parser.add_argument("--out-format", dest="output_format", choices=["tsv", "json", "jsonl"])
    parser.add_argument("--chunk-size", dest="chunk_size", type=int, default=25)
    parser.add_argument("--workers", dest="workers", type=int, default=1)
    return parser.parse_args()


def _resolve_format(path: Path, override: str | None) -> str:
    if override:
        return override
    suffix = path.suffix.lower().lstrip(".")
    if suffix in {"tsv", "json", "jsonl"}:
        return suffix
    raise ValueError(f"Unsupported file format for {path}")


def _parse_segments(parser: FoundryParser, path: Path, fmt: str) -> list[TranslationSegment]:
    parser_map = {
        "tsv": parser.parse_tsv,
        "json": parser.parse_json,
        "jsonl": parser.parse_jsonl,
    }
    parser_func = parser_map.get(fmt)
    if parser_func:
        return parser_func(path)
    raise ValueError(f"Unsupported input format: {fmt}")


def _build_engine() -> TranslationEngine:
    return TranslationEngine(DummyLLM())


def _translate_segment(segment: TranslationSegment, engine: TranslationEngine) -> TranslationSegment:
    engine.translate_single_segment(
        segment,
        target_lang="xx",
        project_name="dummy",
        glossary="",
        style="",
        forbidden="",
        temp=0.1,
        strict=True,
        prompt_template="",
    )
    return segment


def _translate_entry(entry: JSONLPipelineEntry) -> JSONLPipelineEntry:
    payload = dict(entry.payload)
    segment = TranslationSegment(
        key=str(payload.get("key", "")),
        source_text=str(payload.get("source", "")),
        context=str(payload.get("note", payload.get("context", "")) or ""),
        translation=str(payload.get("translation", "") or ""),
        original_row=payload,
        ai_draft=str(payload.get("ai_draft", "") or ""),
        provider_id=payload.get("provider_id"),
        remote_id=payload.get("remote_id"),
        last_sync=payload.get("last_sync"),
    )
    _translate_segment(segment)
    payload["translation"] = segment.translation
    return JSONLPipelineEntry(order=entry.order, payload=payload)


def _translate_jsonl(
    segments: list[TranslationSegment],
    output_path: Path,
    chunk_size: int,
    workers: int,
) -> None:
    def process_chunk(entries: list[JSONLPipelineEntry]) -> list[JSONLPipelineEntry]:
        if workers <= 1:
            return [_translate_entry(entry) for entry in entries]
        with ThreadPoolExecutor(max_workers=workers) as executor:
            return list(executor.map(_translate_entry, entries))

    for _ in run_ordered_jsonl_pipeline(
        segments=segments,
        chunk_size=chunk_size,
        process_chunk=process_chunk,
        output_path=output_path,
        single_thread=True,
    ):
        continue


def _translate_batch(
    segments: list[TranslationSegment],
    chunk_size: int,
    workers: int,
) -> None:
    for chunk in iter_segment_chunks(segments, chunk_size):
        if workers <= 1:
            for segment in chunk:
                _translate_segment(segment)
        else:
            with ThreadPoolExecutor(max_workers=workers) as executor:
                list(executor.map(_translate_segment, chunk))


def main() -> int:
    args = _parse_args()
    input_path = Path(args.input_path)
    output_path = Path(args.output_path)

    input_format = _resolve_format(input_path, args.input_format)
    output_format = _resolve_format(output_path, args.output_format)

    if args.chunk_size <= 0:
        raise ValueError("chunk-size must be a positive integer")
    if args.workers <= 0:
        raise ValueError("workers must be a positive integer")

    parser = FoundryParser()
    segments = _parse_segments(parser, input_path, input_format)

    if output_format == "jsonl":
        _translate_jsonl(
            segments,
            output_path,
            chunk_size=args.chunk_size,
            workers=args.workers,
        )
        return 0

    _translate_batch(segments, chunk_size=args.chunk_size, workers=args.workers)
    parser.save_path(segments, output_path, output_format)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
