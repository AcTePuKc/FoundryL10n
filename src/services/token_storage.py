from __future__ import annotations

import json
from pathlib import Path
from typing import Any
import importlib


DEFAULT_SERVICE_NAME = "FoundryL10n"
DEFAULT_STORAGE_PATH = Path.home() / ".foundryl10n_tokens.json"


class TokenStorage:
    def __init__(
        self,
        *,
        service_name: str = DEFAULT_SERVICE_NAME,
        storage_path: Path | None = None,
        keyring_module: Any | None = None,
    ) -> None:
        self.service_name = service_name
        self.storage_path = storage_path or DEFAULT_STORAGE_PATH
        self._keyring = keyring_module if keyring_module is not None else self._load_keyring()
        self._keyring_errors = self._load_keyring_errors()

    def get_token(self, provider_id: str) -> str | None:
        token = self._read_keyring(provider_id)
        if token is not None:
            return token
        data = self._read_fallback()
        return data.get(provider_id)

    def set_token(self, provider_id: str, token: str) -> None:
        if self._write_keyring(provider_id, token):
            return
        data = self._read_fallback()
        data[provider_id] = token
        self._write_fallback(data)

    def clear_token(self, provider_id: str) -> None:
        if self._delete_keyring(provider_id):
            return
        data = self._read_fallback()
        if provider_id in data:
            data.pop(provider_id, None)
            self._write_fallback(data)

    def _load_keyring(self) -> Any | None:
        if importlib.util.find_spec("keyring") is None:
            return None
        return importlib.import_module("keyring")

    def _load_keyring_errors(self) -> Any | None:
        if importlib.util.find_spec("keyring.errors") is None:
            return None
        return importlib.import_module("keyring.errors")

    def _read_keyring(self, provider_id: str) -> str | None:
        if self._keyring is None:
            return None
        error_types = self._keyring_error_types()
        if error_types:
            try:
                return self._keyring.get_password(self.service_name, provider_id)
            except error_types:
                return None
        return self._keyring.get_password(self.service_name, provider_id)

    def _write_keyring(self, provider_id: str, token: str) -> bool:
        if self._keyring is None:
            return False
        error_types = self._keyring_error_types()
        if error_types:
            try:
                self._keyring.set_password(self.service_name, provider_id, token)
            except error_types:
                return False
        else:
            self._keyring.set_password(self.service_name, provider_id, token)
        return True

    def _delete_keyring(self, provider_id: str) -> bool:
        if self._keyring is None:
            return False
        error_types = self._keyring_error_types()
        if error_types:
            try:
                self._keyring.delete_password(self.service_name, provider_id)
            except error_types:
                return False
        else:
            self._keyring.delete_password(self.service_name, provider_id)
        return True

    def _read_fallback(self) -> dict[str, str]:
        if not self.storage_path.exists():
            return {}
        try:
            raw = self.storage_path.read_text(encoding="utf-8")
            payload = json.loads(raw)
        except (OSError, json.JSONDecodeError):
            return {}
        if isinstance(payload, dict):
            return {str(k): str(v) for k, v in payload.items()}
        return {}

    def _write_fallback(self, data: dict[str, str]) -> None:
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.storage_path.write_text(
            json.dumps(data, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def _keyring_error_types(self) -> tuple[type[Exception], ...]:
        if self._keyring_errors is None:
            return ()
        errors = self._keyring_errors
        candidates = []
        for name in ("KeyringError", "PasswordDeleteError", "PasswordSetError"):
            error_type = getattr(errors, name, None)
            if isinstance(error_type, type) and issubclass(error_type, Exception):
                candidates.append(error_type)
        return tuple(candidates)
