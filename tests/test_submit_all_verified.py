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


def test_submit_all_verified_explicit_trigger(qapp, qsettings, monkeypatch):
    monkeypatch.setattr(LLMService, "get_models", lambda self: ["model-a"])
    registry = _build_registry()

    submitted = []

    def fake_submit(self, token, *, segment_id, suggestion_text):
        submitted.append(segment_id)
        return {"ok": True}

    monkeypatch.setattr(ProviderHttpClient, "submit_suggestion", fake_submit)

    window = FoundryGUI(plugin_registry=registry)
    index = window.settings_tab.provider_dropdown.findData("demo")
    window.settings_tab.provider_dropdown.setCurrentIndex(index)
    qapp.processEvents()
    window.token_storage.set_token("demo", "token-123")
    window.update_sync_action_state()

    verified_segment = TranslationSegment(
        key="seg-verified",
        source_text="Source A",
        translation="Target A",
        original_row={"segment_id": "seg-1"},
    )
    verified_segment.is_verified = True
    unverified_segment = TranslationSegment(
        key="seg-unverified",
        source_text="Source B",
        translation="Target B",
        original_row={"segment_id": "seg-2"},
    )
    unverified_segment.is_verified = False
    verified_missing_id = TranslationSegment(
        key="seg-missing",
        source_text="Source C",
        translation="Target C",
        original_row={},
    )
    verified_missing_id.is_verified = True

    window.segments = [verified_segment, unverified_segment, verified_missing_id]

    assert submitted == []
    window.action_submit_verified.trigger()
    assert submitted == ["seg-1"]
    window.close()
