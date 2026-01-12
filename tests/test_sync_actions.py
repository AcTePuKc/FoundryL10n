import pytest

PySide6 = pytest.importorskip("PySide6")

from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from core.parser import TranslationSegment
from services.llm_service import LLMService
from services.plugin_loader import PluginEntry, PluginRegistry
from services.provider_http_client import ProviderHttpClient
from ui.main_window import FoundryGUI


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


def _build_registry() -> PluginRegistry:
    plugin_data = {
        "metadata": {"id": "demo", "name": "Demo", "base_url": "https://example.com"},
        "auth": {"type": "bearer"},
        "endpoints": {
            "fetch_segments": "/segments",
            "submit_suggestion": "/segments/{segment_id}/suggestions",
        },
    }
    entry = PluginEntry(
        path=Path("demo.json"),
        name="Demo",
        metadata_id="demo",
        data=plugin_data,
        errors=(),
    )
    return PluginRegistry(
        providers={"demo": plugin_data},
        entries=(entry,),
        warnings=(),
    )


def test_sync_actions_require_auth(qapp, qsettings, monkeypatch):
    monkeypatch.setattr(LLMService, "get_models", lambda self: ["model-a"])
    registry = _build_registry()

    window = FoundryGUI(plugin_registry=registry)
    index = window.settings_tab.provider_dropdown.findData("demo")
    assert index >= 0
    window.settings_tab.provider_dropdown.setCurrentIndex(index)
    qapp.processEvents()

    assert not window.action_fetch_segments.isEnabled()
    assert not window.action_submit_suggestion.isEnabled()

    window.token_storage.set_token("demo", "token-123")
    window.update_sync_action_state()
    assert window.action_fetch_segments.isEnabled()
    assert window.action_submit_suggestion.isEnabled()
    window.close()


def test_sync_actions_user_triggered(qapp, qsettings, monkeypatch):
    monkeypatch.setattr(LLMService, "get_models", lambda self: ["model-a"])
    registry = _build_registry()

    calls = {"fetch": 0, "submit": 0}

    def fake_fetch(self, token, *, project_id=None, page=None):
        calls["fetch"] += 1
        return []

    def fake_submit(self, token, *, segment_id, suggestion_text):
        calls["submit"] += 1
        return {"ok": True}

    monkeypatch.setattr(ProviderHttpClient, "fetch_segments", fake_fetch)
    monkeypatch.setattr(ProviderHttpClient, "submit_suggestion", fake_submit)

    window = FoundryGUI(plugin_registry=registry)
    index = window.settings_tab.provider_dropdown.findData("demo")
    window.settings_tab.provider_dropdown.setCurrentIndex(index)
    qapp.processEvents()
    window.token_storage.set_token("demo", "token-123")
    window.update_sync_action_state()

    seg = TranslationSegment(
        key="seg-key",
        source_text="Source",
        translation="Target",
        original_row={"segment_id": "seg-1"},
    )
    window.segments = [seg]
    window.current_row = 0

    assert calls == {"fetch": 0, "submit": 0}
    window.action_fetch_segments.trigger()
    window.action_submit_suggestion.trigger()
    assert calls == {"fetch": 1, "submit": 1}
    window.close()
