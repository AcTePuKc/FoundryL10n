from __future__ import annotations

import sys
from pathlib import Path
from typing import cast

from PySide6.QtWidgets import QApplication
from rich import print

from core.i18n import I18N


def _get_base_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS"))
    return Path(__file__).resolve().parents[2]


def load_theme(theme_name: str) -> None:
    theme_path = _get_base_path() / "resources" / "themes" / f"{theme_name}.qss"
    if not theme_path.exists():
        print(I18N.t("cli_theme_missing_warning").format(theme_path=theme_path))
        return

    qss_text = theme_path.read_text(encoding="utf-8")

    app = QApplication.instance()
    if app is None:
        raise RuntimeError(I18N.t("cli_qapp_missing_error"))

    qt_app = cast(QApplication, app)
    qt_app.setStyleSheet(qss_text)


def get_available_themes() -> list[str]:
    theme_dir = _get_base_path() / "resources" / "themes"
    if not theme_dir.exists():
        return ["dark"]
    return sorted({theme.stem for theme in theme_dir.glob("*.qss")})
