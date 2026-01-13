import pytest

pytest.importorskip("ollama")

from services.llm_service import LLMService


def test_check_connection_success(monkeypatch):
    class FakeClient:
        def list(self):
            return {"models": []}

    monkeypatch.setattr(
        "services.llm_service.ollama.Client",
        lambda **kwargs: FakeClient(),
    )
    service = LLMService()

    ok, error = service.check_connection()

    assert ok is True
    assert error is None


def test_check_connection_failure(monkeypatch):
    def _raise_error():
        raise RuntimeError("no server")

    class FakeClient:
        def list(self):
            _raise_error()

    monkeypatch.setattr(
        "services.llm_service.ollama.Client",
        lambda **kwargs: FakeClient(),
    )
    service = LLMService()

    ok, error = service.check_connection()

    assert ok is False
    assert "no server" in error
