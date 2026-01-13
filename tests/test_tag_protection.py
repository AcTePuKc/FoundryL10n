import pytest

pytest.importorskip("ollama")

from core.engine import TranslationEngine
from core.masker import Masker
from services.llm_service import validate_placeholders


class DummyLLM:
    def __init__(self, response: str):
        self.response = response

    def translate_segment(self, **_kwargs):
        return self.response, ""


class DummySegment:
    def __init__(self, source_text: str):
        self.source_text = source_text
        self.translation = ""
        self.is_verified = False
        self.never_translate = False
        self.ai_draft = ""
        self.thought = ""


def test_placeholder_preservation():
    masker = Masker()
    source = "Hello {player_name}, you have %d gold in your <color=yellow>pouch</color>!"
    masked, tokens = masker.mask(source)
    translated = (
        "Здрасти @@PLACEHOLDER_0@@, имаш @@PLACEHOLDER_1@@ злато в "
        "@@PLACEHOLDER_2@@торбата@@PLACEHOLDER_3@@!"
    )

    assert validate_placeholders(masked, translated)

    unmasked = masker.unmask(translated, tokens)
    assert "{player_name}" in unmasked
    assert "%d" in unmasked
    assert "<color=yellow>" in unmasked
    assert "</color>" in unmasked


def test_tag_error_when_placeholder_missing():
    engine = TranslationEngine(DummyLLM("Здравей!"))
    segment = DummySegment("Hello {player_name}!")

    success = engine.translate_single_segment(
        segment,
        target_lang="BG",
        project_name="default",
        glossary="",
        style="",
        forbidden="",
        temp=0.1,
        strict=True,
        prompt_template="{source}",
    )

    assert success
    assert segment.translation.startswith("[TAG ERROR]")
