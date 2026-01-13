import pytest

pytest.importorskip("ollama")
pytest.importorskip("PySide6")

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

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


def test_llm_timeout_setting_persists_and_passes(qapp, qsettings, monkeypatch):
    monkeypatch.setattr(LLMService, "check_connection", lambda self: (True, None))
    monkeypatch.setattr(LLMService, "get_models", lambda self: ["model-a"])

    tab = SettingsTab()
    tab.llm_timeout_spin.setValue(12.5)
    tab.save_settings()

    new_tab = SettingsTab()
    assert new_tab.llm_timeout_spin.value() == 12.5

    captured = {}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            captured["timeout"] = kwargs.get("timeout")

    monkeypatch.setattr(
        "services.llm_service.ollama.Client",
        lambda **kwargs: FakeClient(**kwargs),
    )

    settings = new_tab.get_settings()
    LLMService(model_name="model-a", timeout=settings["llm_timeout"])

    assert captured["timeout"] == settings["llm_timeout"]
