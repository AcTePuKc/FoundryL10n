from core.engine import TranslationEngine
from core.parser import TranslationSegment


class DummyLLM:
    def __init__(self, translate_responses: list[str], repair_response: str):
        self.translate_responses = translate_responses
        self.repair_response = repair_response
        self.repair_calls: list[tuple[str, str, list[str]]] = []

    def translate_segment(self, *args, **kwargs):
        if self.translate_responses:
            return self.translate_responses.pop(0), ""
        return "", ""

    def repair_placeholders(
        self,
        source_line: str,
        candidate_translation: str,
        expected_placeholders: list[str],
    ):
        self.repair_calls.append(
            (source_line, candidate_translation, list(expected_placeholders))
        )
        return self.repair_response, ""


def test_repair_loop_fixes_extra_placeholder():
    llm = DummyLLM(
        translate_responses=["Здравей <BR_1> ", "!"],
        repair_response="Здравей {name}!",
    )
    engine = TranslationEngine(llm)
    seg = TranslationSegment("seg-1", "Hello {name}!")

    engine.translate_single_segment(
        seg,
        target_lang="BG",
        project_name="default",
        glossary="",
        style="",
        forbidden="",
        temp=0.1,
        strict=True,
        prompt_template="",
    )

    assert "{name}" in seg.translation
    assert "<BR_1>" not in seg.translation
    assert "[TAG ERROR]" not in seg.translation
    assert seg.repair_attempted
    assert seg.repair_success
    assert not seg.repair_failed
    assert len(llm.repair_calls) == 1


def test_repair_loop_failure_keeps_tag_error():
    llm = DummyLLM(
        translate_responses=["Здравей <BR_1> ", "!"],
        repair_response="Здравей!",
    )
    engine = TranslationEngine(llm)
    seg = TranslationSegment("seg-2", "Hello {name}!")

    engine.translate_single_segment(
        seg,
        target_lang="BG",
        project_name="default",
        glossary="",
        style="",
        forbidden="",
        temp=0.1,
        strict=True,
        prompt_template="",
    )

    assert seg.translation.startswith("[TAG ERROR]")
    assert seg.repair_attempted
    assert not seg.repair_success
    assert seg.repair_failed
