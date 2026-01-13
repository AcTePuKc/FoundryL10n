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
    alpha = {"metadata": {"id": "alpha", "name": "Alpha"}}
    entries = (
        PluginEntry(
            path="alpha.json",
            name="Alpha",
            metadata_id="alpha",
            data=alpha,
            errors=(),
        ),
    )
    return PluginRegistry(
        providers={"alpha": alpha},
        entries=entries,
        warnings=(),
    )


def _select_provider(window: FoundryGUI) -> None:
    index = window.settings_tab.provider_dropdown.findData("alpha")
    window.settings_tab.provider_dropdown.setCurrentIndex(index)


def test_ctrl_enter_advances_once_in_provider_context(
    qapp,
    qsettings,
    core_db,
    monkeypatch,
):
    monkeypatch.setattr(LLMService, "get_models", lambda self: ["model-a"])
    registry = _build_registry()

    window = FoundryGUI(plugin_registry=registry)
    try:
        _select_provider(window)
        qapp.processEvents()
        window.token_storage.set_token("alpha", "token-123")
        assert window.get_project_context()["mode"] == "remote-synced"

        segments = [
            TranslationSegment(
                key="seg-1",
                source_text="Hello",
                translation="",
                is_verified=False,
                provider_id="alpha",
            ),
            TranslationSegment(
                key="seg-2",
                source_text="World",
                translation="",
                is_verified=False,
                provider_id="alpha",
            ),
            TranslationSegment(
                key="seg-3",
                source_text="Again",
                translation="",
                is_verified=False,
                provider_id="alpha",
            ),
        ]
        window._load_segments_into_table(segments)
        window.table.setCurrentCell(0, 1)
        qapp.processEvents()

        window.editor.trans_edit.setPlainText("Bonjour")
        QTest.keyClick(
            window.editor.trans_edit,
            Qt.Key.Key_Return,
            Qt.KeyboardModifier.ControlModifier,
        )
        qapp.processEvents()

        assert segments[0].translation == "Bonjour"
        assert segments[0].is_verified is True
        assert window.table.currentRow() == 1
        assert window.current_row == 1
    finally:
        window.close()


def test_focus_modes_preserve_provider_context(
    qapp,
    qsettings,
    core_db,
    monkeypatch,
):
    monkeypatch.setattr(LLMService, "get_models", lambda self: ["model-a"])
    registry = _build_registry()

    window = FoundryGUI(plugin_registry=registry)
    try:
        _select_provider(window)
        qapp.processEvents()
        window.token_storage.set_token("alpha", "token-123")
        assert window.get_project_context()["mode"] == "remote-synced"

        window.btn_reverse_zen.click()
        qapp.processEvents()
        assert window.btn_reverse_zen.isChecked() is True
        assert window.table.isVisible() is False
        assert window.editor_container.isVisible() is True
        assert window.get_project_context()["mode"] == "remote-synced"

        window.btn_reverse_zen.click()
        qapp.processEvents()
        assert window.btn_reverse_zen.isChecked() is False
        assert window.table.isVisible() is True

        window.btn_zen.click()
        qapp.processEvents()
        assert window.btn_zen.isChecked() is True
        assert window.editor_container.isVisible() is False
        assert window.table.isVisible() is True
        assert window.get_project_context()["mode"] == "remote-synced"
    finally:
        window.close()
