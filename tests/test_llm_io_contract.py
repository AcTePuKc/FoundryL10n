import pytest

from core.llm_io_contract import LLMContractError, extract_response_text


def test_extract_response_text_from_string():
    assert extract_response_text("  hello world  ") == "hello world"


def test_extract_response_text_from_mapping():
    payload = {"response": "  mapped response  "}

    assert extract_response_text(payload) == "mapped response"


def test_extract_response_text_from_response_attribute():
    class DummyResponse:
        def __init__(self, response: str) -> None:
            self.response = response

    assert extract_response_text(DummyResponse("  attribute response  ")) == "attribute response"


def test_extract_response_text_from_model_dump():
    class DummyResponse:
        def model_dump(self):
            return {"response": "  dumped response  "}

    assert extract_response_text(DummyResponse()) == "dumped response"


def test_extract_response_text_rejects_invalid_payload():
    class Unsupported:
        pass

    with pytest.raises(LLMContractError):
        extract_response_text(Unsupported())
