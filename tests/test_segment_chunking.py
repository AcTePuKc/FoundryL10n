from core.parser import TranslationSegment
from core.translation_pipeline import iter_segment_chunks


def _make_segments(count: int) -> list[TranslationSegment]:
    return [
        TranslationSegment(key=f"seg-{index}", source_text=f"Source {index}")
        for index in range(count)
    ]


def test_iter_segment_chunks_empty_input() -> None:
    segments: list[TranslationSegment] = []
    assert list(iter_segment_chunks(segments, 2)) == []


def test_iter_segment_chunks_smaller_than_chunk_size() -> None:
    segments = _make_segments(2)
    chunks = list(iter_segment_chunks(segments, 5))

    assert len(chunks) == 1
    assert [segment.key for segment in chunks[0]] == ["seg-0", "seg-1"]


def test_iter_segment_chunks_exact_multiple() -> None:
    segments = _make_segments(4)
    chunks = list(iter_segment_chunks(segments, 2))

    assert len(chunks) == 2
    assert [segment.key for segment in chunks[0]] == ["seg-0", "seg-1"]
    assert [segment.key for segment in chunks[1]] == ["seg-2", "seg-3"]


def test_iter_segment_chunks_includes_last_partial_batch() -> None:
    segments = _make_segments(5)
    chunks = list(iter_segment_chunks(segments, 2))

    assert len(chunks) == 3
    assert [segment.key for segment in chunks[0]] == ["seg-0", "seg-1"]
    assert [segment.key for segment in chunks[1]] == ["seg-2", "seg-3"]
    assert [segment.key for segment in chunks[2]] == ["seg-4"]
