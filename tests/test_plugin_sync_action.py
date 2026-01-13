import pytest

PySide6 = pytest.importorskip("PySide6")

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from services.llm_service import LLMService
from services.plugin_sync_service import PluginSyncResult

ui_main_window = pytest.importorskip(
    "ui.main_window",
    reason="UI imports failed; skipping plugin sync action tests",
)
FoundryGUI = ui_main_window.FoundryGUI


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


def test_plugin_sync_action_calls_service(qapp, qsettings, monkeypatch):
    monkeypatch.setattr(LLMService, "get_models", lambda self: ["model-a"])
    calls = {"count": 0}

    def fake_sync(self, *, allow_overwrite=False):
        calls["count"] += 1
        return PluginSyncResult((), (), (), (), ())

    monkeypatch.setattr(
        "ui.main_window.GitHubPluginSyncService.sync_plugins", fake_sync
    )

    window = FoundryGUI(plugin_registry=None)
    assert calls["count"] == 0
    window.action_sync_plugins.trigger()
    assert calls["count"] == 1
    window.close()
