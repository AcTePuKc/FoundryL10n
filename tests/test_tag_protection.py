from core.rlm_segmenter import RLMSegmenter
from core.rlm_validator import validate_segments


def _segment(line: str):
    segmenter = RLMSegmenter()
    return segmenter.segment(raw_line=line)


def test_validator_accepts_preserved_tags():
    source = "Use <TSMARKER_0> then [ACTION_SAVE] and <BR_1> {player_name} %d."
    target = "Използвай <TSMARKER_0> после [ACTION_SAVE] и <BR_1> {player_name} %d."

    source_result = _segment(source)
    target_result = _segment(target)
    validation = validate_segments(
        source_segments=source_result.segments,
        target_segments=target_result.segments,
        source_tags=source_result.tags,
        target_tags=target_result.tags,
    )

    assert validation.is_valid


def test_validator_flags_missing_tag():
    source = "Click <TSMARKER_0> then [ACTION_SAVE] <BR_1>."
    target = "Натисни <TSMARKER_0> после <BR_1>."

    source_result = _segment(source)
    target_result = _segment(target)
    validation = validate_segments(
        source_segments=source_result.segments,
        target_segments=target_result.segments,
        source_tags=source_result.tags,
        target_tags=target_result.tags,
    )

    assert not validation.is_valid
    assert "missing_tag" in validation.risk_flags


def test_validator_flags_reordered_tags():
    source = "Pick <SPAN_0> then <BR_1> and [ACTION_RUN]."
    target = "Избери <BR_1> после <SPAN_0> и [ACTION_RUN]."

    source_result = _segment(source)
    target_result = _segment(target)
    validation = validate_segments(
        source_segments=source_result.segments,
        target_segments=target_result.segments,
        source_tags=source_result.tags,
        target_tags=target_result.tags,
    )

    assert not validation.is_valid
    assert "reordered_tags" in validation.risk_flags
