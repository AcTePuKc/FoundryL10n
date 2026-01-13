import pytest

PySide6 = pytest.importorskip("PySide6")

from PySide6.QtCore import QSettings
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


def test_translation_segment_remote_changed_default_false():
    seg = TranslationSegment(key="seg-1", source_text="Source")
    assert hasattr(seg, "remote_changed")
    assert seg.remote_changed is False


def test_remote_changed_flag_marks_segment(qapp, qsettings, monkeypatch):
    monkeypatch.setattr(LLMService, "get_models", lambda self: ["model-a"])
    window = FoundryGUI()
    seg = TranslationSegment(key="seg-2", source_text="Source")
    seg.remote_changed = True
    window._load_segments_into_table([seg])
    window._remote_change_ready = True
    window.update_row_visuals(0)

    state_item = window.table.item(0, 0)
    assert "⚠️" in state_item.text()
    window.close()
