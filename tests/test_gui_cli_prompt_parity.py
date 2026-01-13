import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from core.parser import TranslationSegment
from services.llm_service import LLMService
from ui.settings_tab import SettingsTab
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


def test_gui_cli_prompt_parity(qapp, qsettings, monkeypatch, tmp_path):
    glossary_path = tmp_path / "glossary.tsv"
    glossary_path.write_text("term\ttranslation\nHero\tГерой\n", encoding="utf-8")
    style_path = tmp_path / "style.md"
    style_path.write_text("Keep it short.", encoding="utf-8")
    forbidden_path = tmp_path / "forbidden.txt"
    forbidden_path.write_text("foo\nbar\n", encoding="utf-8")

    tab = SettingsTab()
    tab.project_name.setText("default")
    tab.on_project_name_committed()
    tab.gloss_path.setText(str(glossary_path))
    tab.style_path.setText(str(style_path))
    tab.forbidden_path.setText(str(forbidden_path))
    tab.prompt_editor.set_text(
        "SRC:{source}\nGLOSS:{glossary}\nSTYLE:{style}\nFORBID:{forbidden}\nCTX:{context}"
    )
    tab.save_settings()

    captured = []

    class DummyClient:
        def generate(self, *, model, prompt, options):
            captured.append(prompt)
            return {"response": "OK"}

    def fake_init(self, model_name="test-model", timeout=None):
        self.model = model_name
        self.timeout = None
        self.client = DummyClient()

    monkeypatch.setattr(LLMService, "__init__", fake_init)

    gui_settings = tab.get_settings()
    gui_segment = TranslationSegment(key="s-1", source_text="Hello @@PLACEHOLDER_0@@")
    gui_worker = TranslationWorker(
        segments=[gui_segment],
        target_lang="BG",
        llm_service=LLMService(model_name="gui-model"),
        glossary_path=gui_settings["glossary_path"],
        style_path=gui_settings["style_path"],
        forbidden_path=gui_settings["forbidden_path"],
        prompt_template=gui_settings["prompt_template"],
        temp=0.1,
        project_name=gui_settings["project_name"],
    )
    gui_worker.run()
    gui_prompt = captured[-1]

    captured.clear()

    main.translate_text(
        content="Hello @@PLACEHOLDER_0@@",
        lang="BG",
        model="cli-model",
        glossary=str(glossary_path),
        style=str(style_path),
        forbidden=str(forbidden_path),
        project="default",
    )
    cli_prompt = captured[-1]

    assert gui_prompt == cli_prompt
