import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from core.parser import TranslationSegment
from services.llm_service import LLMService
from ui.worker import TranslationWorker

import main


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def qsettings(tmp_path):
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(tmp_path))
    QSettings.setPath(QSettings.IniFormat, QSettings.SystemScope, str(tmp_path))
    settings = QSettings("FoundryL10n", "TranslatorApp")
    settings.clear()
    settings.sync()
    yield settings
    settings.clear()
    settings.sync()


def test_gui_cli_tag_preservation_parity(
    qapp, qsettings, monkeypatch, tmp_path, capsys
):
    glossary_path = tmp_path / "glossary.tsv"
    glossary_path.write_text("term\ttranslation\nHero\tГерой\n", encoding="utf-8")
    style_path = tmp_path / "style.md"
    style_path.write_text("Keep it short.", encoding="utf-8")
    forbidden_path = tmp_path / "forbidden.txt"
    forbidden_path.write_text("foo\nbar\n", encoding="utf-8")

    def fake_init(self, model_name="test-model", timeout=None):
        self.model = model_name
        self.timeout = None
        self.client = None

    def fake_translate_segment(
        self,
        *,
        text,
        target_lang,
        project_name="default",
        glossary="",
        style="",
        forbidden="",
        temp=0.1,
        prompt_template="",
        current_translation="",
        context_extra="",
    ):
        return text, ""

    monkeypatch.setattr(LLMService, "__init__", fake_init)
    monkeypatch.setattr(LLMService, "translate_segment", fake_translate_segment)

    source = "Hello {player_name}, <color=yellow>%d</color>!"
    gui_segment = TranslationSegment(key="s-1", source_text=source)
    gui_worker = TranslationWorker(
        segments=[gui_segment],
        target_lang="BG",
        llm_service=LLMService(model_name="gui-model"),
        glossary_path=str(glossary_path),
        style_path=str(style_path),
        forbidden_path=str(forbidden_path),
        prompt_template="{source}",
        temp=0.1,
        project_name="default",
    )
    gui_worker.run()

    expected_translation = gui_segment.translation
    assert "{player_name}" in expected_translation
    assert "<color=yellow>" in expected_translation
    assert "%d" in expected_translation

    capsys.readouterr()
    main.translate_text(
        content=source,
        lang="BG",
        model="cli-model",
        glossary=str(glossary_path),
        style=str(style_path),
        forbidden=str(forbidden_path),
        project="default",
    )
    output = capsys.readouterr().out

    assert expected_translation in output
