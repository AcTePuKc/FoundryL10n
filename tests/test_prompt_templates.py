import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from core.engine import TranslationEngine
from core.parser import TranslationSegment
from services.llm_service import LLMService
from ui.settings_tab import SettingsTab


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


@pytest.fixture
def llm_ready(monkeypatch):
    monkeypatch.setattr(LLMService, "check_connection", lambda self: (False, "offline"))


def test_prompt_template_persists_per_project(qapp, qsettings, llm_ready):
    tab = SettingsTab()

    tab.project_name.setText("Alpha")
    tab.on_project_name_committed()
    tab.prompt_editor.set_text("alpha {source}")
    tab.save_settings()

    tab.project_name.setText("Beta")
    tab.on_project_name_committed()
    tab.prompt_editor.set_text("beta {source}")
    tab.save_settings()

    new_tab = SettingsTab()
    assert new_tab.prompt_editor.get_text() == "beta {source}"

    new_tab.project_name.setText("Alpha")
    new_tab.on_project_name_committed()
    assert new_tab.prompt_editor.get_text() == "alpha {source}"


def test_prompt_template_reaches_llm_service(qapp, qsettings, llm_ready, monkeypatch):
    tab = SettingsTab()
    tab.prompt_editor.set_text("custom {source}")
    settings = tab.get_settings()

    captured = {}

    def fake_translate(self, **kwargs):
        captured["prompt_template"] = kwargs.get("prompt_template")
        return "OK", ""

    monkeypatch.setattr(LLMService, "translate_segment", fake_translate)

    engine = TranslationEngine(LLMService(model_name="model-a"))
    segment = TranslationSegment(key="id-1", source_text="Hello")

    engine.translate_single_segment(
        segment,
        target_lang="BG",
        project_name="Alpha",
        glossary="",
        style="",
        forbidden="",
        temp=0.1,
        strict=True,
        prompt_template=settings["prompt_template"],
    )

    assert captured["prompt_template"] == "custom {source}"
