import pytest
from pathlib import Path
from unittest.mock import Mock

PySide6 = pytest.importorskip("PySide6")

from PySide6.QtCore import QSettings
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


def test_import_tsv_calls_parser_and_updates_ui(qapp, qsettings, monkeypatch, tmp_path):
    monkeypatch.setattr(LLMService, "get_models", lambda self: ["model-a"])
    window = FoundryGUI()

    segments = [TranslationSegment(key="seg-1", source_text="Source")]
    parse_mock = Mock(return_value=segments)
    window._tsv_parser.parse_tsv = parse_mock

    path = tmp_path / "input.tsv"
    window.import_tsv_path(path)

    parse_mock.assert_called_once_with(path)
    assert window.input_path == path
    assert window._file_loaded is True
    assert window.file_label.text() == str(path)
    assert window.table.rowCount() == 1
    window.close()


def test_export_tsv_calls_parser_and_updates_ui(qapp, qsettings, monkeypatch, tmp_path):
    monkeypatch.setattr(LLMService, "get_models", lambda self: ["model-a"])
    window = FoundryGUI()

    segments = [TranslationSegment(key="seg-1", source_text="Source")]
    window.segments = segments
    save_mock = Mock()
    window._tsv_parser.save_tsv = save_mock

    out_path = tmp_path / "output.tsv"
    window.export_tsv_path(out_path)

    save_mock.assert_called_once_with(segments, out_path)
    assert window.file_label.text() == I18N.t("msg_file_saved").format(path=out_path)
    window.close()
