import pytest

pytest.importorskip("ollama")

from services.llm_service import LLMService


def test_check_connection_success(monkeypatch):
    service = LLMService()
    monkeypatch.setattr("services.llm_service.ollama.list", lambda: {"models": []})

    ok, error = service.check_connection()

    assert ok is True
    assert error is None


def test_check_connection_failure(monkeypatch):
    service = LLMService()

    def _raise_error():
        raise RuntimeError("no server")

    monkeypatch.setattr("services.llm_service.ollama.list", _raise_error)

    ok, error = service.check_connection()

    assert ok is False
    assert "no server" in error
