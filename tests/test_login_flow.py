from __future__ import annotations

from pathlib import Path

import pytest

PySide6 = pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication

from services.token_storage import TokenStorage
from ui.login_dialog import LoginDialog


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.mark.parametrize(
    "auth_type,expected",
    [
        ("basic", {"username", "password"}),
        ("bearer", {"token"}),
        ("oauth2", {"client_id", "client_secret"}),
    ],
)
def test_login_dialog_fields(qapp: QApplication, auth_type: str, expected: set[str]) -> None:
    dialog = LoginDialog("Demo", auth_type)
    assert set(dialog.fields.keys()) == expected
    dialog.close()


def test_token_storage_fallback(tmp_path: Path) -> None:
    storage = TokenStorage(storage_path=tmp_path / "tokens.json", keyring_module=None)
    storage.set_token("demo", "token-123")
    assert storage.get_token("demo") == "token-123"
    storage.clear_token("demo")
    assert storage.get_token("demo") is None


def test_token_storage_prefers_keyring(tmp_path: Path) -> None:
    pytest.importorskip("keyring")

    class DummyKeyring:
        def __init__(self) -> None:
            self.store: dict[str, str] = {}

        def get_password(self, service: str, username: str) -> str | None:
            return self.store.get(f"{service}:{username}")

        def set_password(self, service: str, username: str, password: str) -> None:
            self.store[f"{service}:{username}"] = password

        def delete_password(self, service: str, username: str) -> None:
            self.store.pop(f"{service}:{username}", None)

    storage = TokenStorage(storage_path=tmp_path / "tokens.json", keyring_module=DummyKeyring())
    storage.set_token("demo", "token-abc")
    assert storage.get_token("demo") == "token-abc"
    assert not (tmp_path / "tokens.json").exists()
