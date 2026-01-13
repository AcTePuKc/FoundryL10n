import json

import pytest

sqlmodel = pytest.importorskip("sqlmodel")
PySide6 = pytest.importorskip("PySide6")

from sqlmodel import Session, create_engine, select

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from core import database
from core.parser import TranslationSegment
from services.llm_service import LLMService
from ui.main_window import FoundryGUI


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture()
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


@pytest.fixture()
def history_db(tmp_path):
    original_engine = database.engine
    test_engine = create_engine(f"sqlite:///{tmp_path / 'history.db'}")
    database.engine = test_engine
    database.init_db()
    try:
        yield database
    finally:
        database.engine = original_engine


def test_history_json_updates_per_segment(history_db):
    history_db.save_translation(
        source_text="Hello",
        target_lang="BG",
        translation="Bonjour",
        project_name="demo",
        segment_key="seg-1",
        verified=False,
    )
    history_db.save_translation(
        source_text="Hello",
        target_lang="BG",
        translation="Salut",
        project_name="demo",
        segment_key="seg-1",
        verified=False,
    )
    history_db.save_translation(
        source_text="Hello",
        target_lang="BG",
        translation="Coucou",
        project_name="demo",
        segment_key="seg-2",
        verified=False,
    )

    with Session(history_db.engine) as session:
        statement = select(history_db.TranslationRecord).where(
            history_db.TranslationRecord.project_name == "demo",
            history_db.TranslationRecord.target_lang == "BG",
            history_db.TranslationRecord.segment_key == "seg-1",
        )
        record = session.exec(statement).first()
        assert record is not None
        assert json.loads(record.history_json) == ["Bonjour"]

        other_statement = select(history_db.TranslationRecord).where(
            history_db.TranslationRecord.project_name == "demo",
            history_db.TranslationRecord.target_lang == "BG",
            history_db.TranslationRecord.segment_key == "seg-2",
        )
        other_record = session.exec(other_statement).first()
        assert other_record is not None
        assert json.loads(other_record.history_json) == []


def test_restore_from_history_keeps_verification_state(
    history_db,
    qapp,
    qsettings,
    monkeypatch,
):
    monkeypatch.setattr(LLMService, "get_models", lambda self: ["model-a"])
    history_db.save_translation(
        source_text="Hello",
        target_lang="BG",
        translation="Bonjour",
        project_name="default",
        segment_key="seg-1",
        verified=True,
    )
    history_db.save_translation(
        source_text="Hello",
        target_lang="BG",
        translation="Salut",
        project_name="default",
        segment_key="seg-1",
        verified=True,
    )

    seg = TranslationSegment(
        key="seg-1",
        source_text="Hello",
        translation="Salut",
        is_verified=True,
    )

    window = FoundryGUI()
    window._load_segments_into_table([seg])
    window.table.setCurrentCell(0, 1)
    window.on_row_selected()

    assert window.editor.history_list.count() == 1
    item = window.editor.history_list.item(0)

    window.restore_from_history_list(item)

    assert window.editor.trans_edit.toPlainText() == "Bonjour"
    assert window.editor.cb_verified.isChecked()
    assert seg.is_verified is True
    window.close()
