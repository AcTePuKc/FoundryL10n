import pytest

PySide6 = pytest.importorskip("PySide6")

from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from core.parser import TranslationSegment
from services.llm_service import LLMService
from services.plugin_loader import PluginEntry, PluginRegistry
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
    alpha = {"metadata": {"id": "alpha", "name": "Alpha"}}
    bravo = {"metadata": {"id": "bravo", "name": "Bravo"}}
    entries = (
        PluginEntry(
            path=Path("alpha.json"),
            name="Alpha",
            metadata_id="alpha",
            data=alpha,
            errors=(),
        ),
        PluginEntry(
            path=Path("bravo.json"),
            name="Bravo",
            metadata_id="bravo",
            data=bravo,
            errors=(),
        ),
    )
    return PluginRegistry(
        providers={"alpha": alpha, "bravo": bravo},
        entries=entries,
        warnings=(),
    )


def test_segment_defaults_are_null():
    seg = TranslationSegment(key="seg-1", source_text="Source")
    assert seg.provider_id is None
    assert seg.remote_id is None


def test_project_context_switches_with_provider(qapp, qsettings, monkeypatch):
    monkeypatch.setattr(LLMService, "get_models", lambda self: ["model-a"])
    registry = _build_registry()

    window = FoundryGUI(plugin_registry=registry)
    assert window.get_project_context()["mode"] == "local-only"

    index = window.settings_tab.provider_dropdown.findData("alpha")
    window.settings_tab.provider_dropdown.setCurrentIndex(index)
    qapp.processEvents()
    window.token_storage.set_token("alpha", "token-123")
    assert window.get_project_context()["mode"] == "remote-synced"

    index = window.settings_tab.provider_dropdown.findData("bravo")
    window.settings_tab.provider_dropdown.setCurrentIndex(index)
    qapp.processEvents()
    assert window.get_project_context()["mode"] == "local-only"
    window.close()


def test_provider_switch_does_not_backfill_local_segments(qapp, qsettings, monkeypatch):
    monkeypatch.setattr(LLMService, "get_models", lambda self: ["model-a"])
    registry = _build_registry()

    window = FoundryGUI(plugin_registry=registry)
    local_segment = TranslationSegment(key="local-1", source_text="Local")
    window.segments = [local_segment]

    index = window.settings_tab.provider_dropdown.findData("alpha")
    window.settings_tab.provider_dropdown.setCurrentIndex(index)
    qapp.processEvents()
    index = window.settings_tab.provider_dropdown.findData("bravo")
    window.settings_tab.provider_dropdown.setCurrentIndex(index)
    qapp.processEvents()

    assert local_segment.provider_id is None
    assert local_segment.remote_id is None
    assert "provider_id" not in local_segment.original_row
    assert "remote_id" not in local_segment.original_row
    window.close()
