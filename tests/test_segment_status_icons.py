import pytest

PySide6 = pytest.importorskip("PySide6")

from PySide6.QtCore import QItemSelectionModel, QSettings, Qt
from PySide6.QtWidgets import QApplication

from core.i18n import I18N
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


def test_stats_counts_with_sync_icons_and_selection(qapp, qsettings, monkeypatch):
    monkeypatch.setattr(LLMService, "get_models", lambda self: ["model-a"])
    window = FoundryGUI()
    seg_verified = TranslationSegment(
        key="verified-1",
        source_text="Verified",
        translation="Done",
    )
    seg_verified.is_verified = True
    seg_draft = TranslationSegment(
        key="draft-1",
        source_text="Draft",
        translation="Draft text",
    )
    window._load_segments_into_table([seg_verified, seg_draft])

    expected_stats = I18N.t("stats_template").format(
        verified=1,
        draft=1,
        risk=0,
        error=0,
        conflict=0,
        pending=0,
    )
    assert window.lbl_stats.text() == expected_stats

    selection_model = window.table.selectionModel()
    index0 = window.table.model().index(0, 0)
    index1 = window.table.model().index(1, 0)
    selection_model.select(
        index0,
        QItemSelectionModel.SelectionFlag.Select
        | QItemSelectionModel.SelectionFlag.Rows,
    )
    selection_model.select(
        index1,
        QItemSelectionModel.SelectionFlag.Select
        | QItemSelectionModel.SelectionFlag.Rows,
    )
    window.update_selection_info()
    expected_selected = I18N.t("stats_selected_template").format(
        count=2,
        stats=expected_stats,
    )
    assert window.lbl_stats.text() == expected_selected

    seg_draft.is_verified = True
    window.update_row_visuals(1)
    window.update_stats()
    expected_after = I18N.t("stats_template").format(
        verified=2,
        draft=0,
        risk=0,
        error=0,
        conflict=0,
        pending=0,
    )
    assert window.lbl_stats.text() == expected_after
    window.close()
