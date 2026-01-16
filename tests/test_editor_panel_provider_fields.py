from __future__ import annotations

import pytest

pytest.importorskip("PySide6", reason="UI tests require PySide6")

from PySide6.QtWidgets import QApplication, QLineEdit

from ui.editor_panel import EditorPanel


def test_build_provider_field_widget_accepts_none_validation() -> None:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    panel = EditorPanel()
    widget = panel._build_provider_field_widget("text", None, "hello")
    assert isinstance(widget, QLineEdit)
    assert widget.text() == "hello"
