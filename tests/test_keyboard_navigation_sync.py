import pytest

sqlmodel = pytest.importorskip("sqlmodel")
PySide6 = pytest.importorskip("PySide6")

try:
    from PySide6.QtCore import Qt, QSettings
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from sqlmodel import create_engine

    from core import database
    from core.parser import TranslationSegment
    from services.llm_service import LLMService
    from services.plugin_loader import PluginEntry, PluginRegistry
    from services.provider_http_client import ProviderHttpClient
    from ui.main_window import FoundryGUI
except Exception as exc:  # pragma: no cover - handled by skip
    pytest.skip(f"UI imports failed: {exc}", allow_module_level=True)


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
def core_db(tmp_path):
    original_engine = database.engine
    test_engine = create_engine(f"sqlite:///{tmp_path / 'core.db'}")
    database.engine = test_engine
    database.init_db()
    try:
        yield database
    finally:
        database.engine = original_engine


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
        path="demo.json",
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


def _select_provider(window: FoundryGUI) -> None:
    index = window.settings_tab.provider_dropdown.findData("demo")
    window.settings_tab.provider_dropdown.setCurrentIndex(index)


def test_sync_actions_preserve_editor_focus_and_shortcuts(
    qapp,
    qsettings,
    core_db,
    monkeypatch,
):
    monkeypatch.setattr(LLMService, "get_models", lambda self: ["model-a"])
    registry = _build_registry()

    def fake_fetch(self, token, *, project_id=None, page=None):
        return [
            {"segment_id": "seg-1", "source": "Source", "target": "Target"},
            {"segment_id": "seg-2", "source": "Next", "target": ""},
        ]

    def fake_submit(self, token, *, segment_id, suggestion_text):
        return {"ok": True}

    monkeypatch.setattr(ProviderHttpClient, "fetch_segments", fake_fetch)
    monkeypatch.setattr(ProviderHttpClient, "submit_suggestion", fake_submit)

    window = FoundryGUI(plugin_registry=registry)
    try:
        _select_provider(window)
        qapp.processEvents()
        window.token_storage.set_token("demo", "token-123")
        window.update_sync_action_state()

        segments = [
            TranslationSegment(
                key="seg-1",
                source_text="Source",
                translation="Target",
                original_row={"segment_id": "seg-1"},
                provider_id="demo",
            ),
            TranslationSegment(
                key="seg-2",
                source_text="Next",
                translation="",
                original_row={"segment_id": "seg-2"},
                provider_id="demo",
            ),
        ]
        window._load_segments_into_table(segments)
        window.table.setCurrentCell(0, 1)
        qapp.processEvents()

        window.editor.trans_edit.setPlainText("Draft")
        window.editor.trans_edit.setFocus()
        qapp.processEvents()
        assert QApplication.focusWidget() is window.editor.trans_edit

        window.action_fetch_segments.trigger()
        qapp.processEvents()
        assert QApplication.focusWidget() is window.editor.trans_edit

        window.table.setCurrentCell(0, 1)
        window.editor.trans_edit.setFocus()
        qapp.processEvents()
        window.action_submit_suggestion.trigger()
        qapp.processEvents()
        assert QApplication.focusWidget() is window.editor.trans_edit

        window.editor.trans_edit.setPlainText("Bonjour")
        QTest.keyClick(
            window.editor.trans_edit,
            Qt.Key.Key_Return,
            Qt.KeyboardModifier.ControlModifier,
        )
        qapp.processEvents()

        assert window.segments[0].translation == "Bonjour"
        assert window.segments[0].is_verified is True
    finally:
        window.close()
