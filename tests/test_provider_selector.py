import pytest

pytest.importorskip("PySide6")

from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from services.llm_service import LLMService
from services.plugin_loader import PluginEntry, PluginRegistry
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


def _build_registry():
    valid_data = {"metadata": {"id": "valid", "name": "Valid"}}
    valid_entry = PluginEntry(
        path=Path("valid.json"),
        name="Valid",
        metadata_id="valid",
        data=valid_data,
        errors=(),
    )
    invalid_entry = PluginEntry(
        path=Path("invalid.json"),
        name="Invalid",
        metadata_id="invalid",
        data=None,
        errors=("invalid schema",),
    )
    return PluginRegistry(
        providers={"valid": valid_data},
        entries=(valid_entry, invalid_entry),
        warnings=(),
    )


def test_provider_selection_persists(qapp, qsettings, monkeypatch):
    monkeypatch.setattr(LLMService, "get_models", lambda self: ["model-a"])
    registry = _build_registry()

    tab = SettingsTab(plugin_registry=registry)
    index = tab.provider_dropdown.findData("valid")
    assert index >= 0
    tab.provider_dropdown.setCurrentIndex(index)
    qapp.processEvents()

    new_tab = SettingsTab(plugin_registry=registry)
    assert new_tab.provider_dropdown.currentData() == "valid"


def test_invalid_provider_is_disabled(qapp, qsettings, monkeypatch):
    monkeypatch.setattr(LLMService, "get_models", lambda self: ["model-a"])
    registry = _build_registry()

    tab = SettingsTab(plugin_registry=registry)
    index = tab.provider_dropdown.findData("invalid")
    assert index >= 0
    model = tab.provider_dropdown.model()
    item = model.item(index) if model is not None else None
    assert item is not None
    assert not item.isEnabled()
