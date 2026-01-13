import csv
from pathlib import Path

import pytest

from core.parser import FoundryParser, TranslationSegment


@pytest.fixture(scope="session")
def qapp():
    PySide6 = pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def qsettings(tmp_path: Path):
    PySide6 = pytest.importorskip("PySide6")
    from PySide6.QtCore import QSettings

    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(tmp_path))
    QSettings.setPath(QSettings.IniFormat, QSettings.SystemScope, str(tmp_path))
    settings = QSettings("FoundryL10n", "TranslatorApp")
    settings.clear()
    settings.sync()
    yield settings
    settings.clear()
    settings.sync()


def test_export_preserves_generic_poc_fields_and_metadata(tmp_path: Path) -> None:
    input_path = tmp_path / "generic_poc.tsv"
    headers = [
        "key",
        "source",
        "translation",
        "notes",
        "segment_id",
        "provider_id",
        "remote_id",
        "last_sync",
    ]
    input_path.write_text(
        "\t".join(headers)
        + "\n"
        + "\t".join(
            [
                "UI_MENU_PLAY",
                "Play",
                "",
                "UI entry",
                "seg-123",
                "generic-poc",
                "remote-555",
                "2024-01-02T03:04:05Z",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    parser = FoundryParser()
    segments = parser.parse_tsv(input_path)
    assert segments[0].key == "UI_MENU_PLAY"

    segments[0].translation = "Jouer"
    output_path = tmp_path / "export.tsv"
    parser.save_tsv(segments, output_path)

    with output_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle, delimiter="\t")
        export_headers = next(reader)
        export_row = next(reader)

    assert export_headers == headers
    export_data = dict(zip(export_headers, export_row))
    assert export_data["translation"] == "Jouer"
    assert export_data["segment_id"] == "seg-123"
    assert export_data["provider_id"] == "generic-poc"
    assert export_data["remote_id"] == "remote-555"
    assert export_data["last_sync"] == "2024-01-02T03:04:05Z"


def test_export_dialog_uses_input_filename(qapp, qsettings, monkeypatch, tmp_path):
    pytest.importorskip("PySide6")

    from services.llm_service import LLMService
    from ui import main_window

    monkeypatch.setattr(LLMService, "get_models", lambda self: ["model-a"])

    selected = {}

    class StubSignal:
        def __init__(self):
            self._callbacks = []

        def connect(self, callback):
            self._callbacks.append(callback)

    class StubDialog:
        class AcceptMode:
            AcceptSave = "accept"

        def __init__(self, *args, **kwargs):
            self.fileSelected = StubSignal()
            self.rejected = StubSignal()
            self.selected = None

        def setAcceptMode(self, mode):
            self.accept_mode = mode

        def setDefaultSuffix(self, suffix):
            self.suffix = suffix

        def setModal(self, modal):
            self.modal = modal

        def selectFile(self, name):
            self.selected = name
            selected["name"] = name

        def open(self):
            return None

    monkeypatch.setattr(main_window, "QFileDialog", StubDialog)
    window = main_window.FoundryGUI()
    window.segments = [TranslationSegment(key="seg-1", source_text="Source")]
    window.input_path = tmp_path / "generic_poc.tsv"

    window.request_tsv_export()

    assert selected["name"] == "generic_poc.tsv"
    window.close()
