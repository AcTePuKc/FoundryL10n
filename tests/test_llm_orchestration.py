import pytest

ollama = pytest.importorskip("ollama")

import services.llm_service as llm_service


@pytest.fixture
def service():
    return llm_service.LLMService(model_name="test-model")


def test_prompt_assembly_includes_source_glossary_style_context(service, monkeypatch):
    captured = {}

    def fake_generate(*, model, prompt, options):
        captured["model"] = model
        captured["prompt"] = prompt
        captured["options"] = options
        return {"response": "OK"}

    monkeypatch.setattr(ollama, "generate", fake_generate)

    prompt_template = "SRC:{source}\nGLOSS:{glossary}\nSTYLE:{style}\nCTX:{context}"

    service.translate_segment(
        text="Hello",
        target_lang="BG",
        project_name="Demo",
        glossary="TERM=Пример",
        style="Keep it short.",
        forbidden="",
        temp=0.2,
        prompt_template=prompt_template,
        current_translation="",
        context_extra="PREV: Greetings",
    )

    assert captured["model"] == "test-model"
    assert "SRC:Hello" in captured["prompt"]
    assert "GLOSS:TERM=Пример" in captured["prompt"]
    assert "STYLE:Keep it short." in captured["prompt"]
    assert "CTX:PREV: Greetings" in captured["prompt"]


def test_context_prefix_added_when_template_missing_context(service, monkeypatch):
    captured = {}

    def fake_generate(*, model, prompt, options):
        captured["prompt"] = prompt
        return {"response": "OK"}

    monkeypatch.setattr(ollama, "generate", fake_generate)

    prompt_template = "SRC:{source}\nGLOSS:{glossary}\nSTYLE:{style}"

    service.translate_segment(
        text="Hello",
        target_lang="BG",
        project_name="Demo",
        glossary="",
        style="",
        forbidden="",
        temp=0.2,
        prompt_template=prompt_template,
        current_translation="",
        context_extra="NEXT: Farewell",
    )

    prefix = llm_service.CONTEXT_PREFIX.format(context="NEXT: Farewell")
    assert captured["prompt"].startswith(prefix)
    assert "SRC:Hello" in captured["prompt"]
