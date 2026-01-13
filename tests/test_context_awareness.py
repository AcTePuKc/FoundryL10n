import pytest

pytest.importorskip("PySide6")
pytest.importorskip("ollama")

from core.engine import TranslationEngine
from core.parser import TranslationSegment
from services.llm_service import LLMService


def test_translate_single_segment_passes_current_translation_and_context(monkeypatch):
    captured = {}

    def fake_translate(self, **kwargs):
        captured["current_translation"] = kwargs.get("current_translation")
        captured["context_extra"] = kwargs.get("context_extra")
        return "OK", ""

    monkeypatch.setattr(LLMService, "translate_segment", fake_translate)

    engine = TranslationEngine(LLMService(model_name="model-a"))
    segment = TranslationSegment(
        key="seg-1",
        source_text="Hello there",
        translation="Existing draft",
    )

    engine.translate_single_segment(
        segment,
        target_lang="BG",
        project_name="Alpha",
        glossary="",
        style="",
        forbidden="",
        temp=0.1,
        strict=True,
        prompt_template="Template {source}",
        context_extra="PREVIOUS: Greetings",
    )

    assert captured["current_translation"] == "Existing draft"
    assert captured["context_extra"] == "PREVIOUS: Greetings"


def test_remote_segments_add_source_and_target_to_context(monkeypatch):
    captured = {}

    def fake_translate(self, **kwargs):
        captured["context_extra"] = kwargs.get("context_extra")
        return "OK", ""

    monkeypatch.setattr(LLMService, "translate_segment", fake_translate)

    engine = TranslationEngine(LLMService(model_name="model-a"))
    segment = TranslationSegment(
        key="remote-1",
        source_text="Source line",
        translation="Remote target",
        provider_id="provider-x",
        remote_id="remote-123",
        original_row={"provider_id": "provider-x", "remote_id": "remote-123"},
    )

    engine.translate_single_segment(
        segment,
        target_lang="BG",
        project_name="Alpha",
        glossary="",
        style="",
        forbidden="",
        temp=0.1,
        strict=True,
        prompt_template="Template {source}",
        context_extra="NEXT: Follow-up",
    )

    assert captured["context_extra"] == (
        "REMOTE SOURCE: Source line\n"
        "REMOTE TARGET: Remote target\n"
        "NEXT: Follow-up"
    )
