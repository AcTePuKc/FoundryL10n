import pytest

PySide6 = pytest.importorskip("PySide6")

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QApplication

from core.parser import TranslationSegment
from services.llm_service import LLMService
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


def test_remote_segment_sync_icon_and_tooltip(qapp, qsettings, monkeypatch):
    monkeypatch.setattr(LLMService, "get_models", lambda self: ["model-a"])
    window = FoundryGUI()
    seg = TranslationSegment(
        key="remote-1",
        source_text="Remote",
        provider_id="alpha",
        remote_id="r-1",
        last_sync="2024-02-10T12:00:00Z",
    )
    window._load_segments_into_table([seg])

    state_item = window.table.item(0, 0)
    assert "☁️" in state_item.text()
    assert "2024-02-10T12:00:00Z" in state_item.toolTip()
    assert not (state_item.flags() & Qt.ItemFlag.ItemIsSelectable)
    window.close()


def test_local_segment_sync_icon_and_tooltip(qapp, qsettings, monkeypatch):
    monkeypatch.setattr(LLMService, "get_models", lambda self: ["model-a"])
    window = FoundryGUI()
    seg = TranslationSegment(key="local-1", source_text="Local")
    window._load_segments_into_table([seg])

    state_item = window.table.item(0, 0)
    assert "🏠" in state_item.text()
    assert "Local" in state_item.toolTip()
    assert not (state_item.flags() & Qt.ItemFlag.ItemIsSelectable)
    window.close()
