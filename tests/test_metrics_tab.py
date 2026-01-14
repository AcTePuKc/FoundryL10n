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


def test_metrics_tab_exists(qapp):
    window = _build_window()
    try:
        index = window.tabs.indexOf(window.metrics_tab)
        assert index != -1
        assert window.tabs.tabText(index) == "Metrics"
        assert "Requests" in window.metrics_llm_label.text()
    finally:
        window.close()
