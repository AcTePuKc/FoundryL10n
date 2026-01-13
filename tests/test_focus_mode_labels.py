import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication


def _build_window():
    try:
        from ui.main_window import FoundryGUI
    except Exception as exc:
        pytest.skip(f"UI imports failed: {exc}")
    return FoundryGUI()


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_focus_mode_labels(qapp):
    window = _build_window()
    try:
        assert window.btn_zen.text() == "Focus: Table"
        assert window.btn_reverse_zen.text() == "Focus: Editor"
    finally:
        window.close()
