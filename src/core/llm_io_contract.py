from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from core.rlm_validator import ValidationResult, validate_placeholder_order


class LLMContractError(ValueError):
    pass


@dataclass(frozen=True)
class LLMRequest:
    model: str
    prompt: str
    options: dict[str, Any]
    request_type: str


def build_request_payload(
    *,
    model: str,
    prompt: str,
    temperature: float,
    stop: Sequence[str],
    request_type: str,
) -> dict[str, Any]:
    if not isinstance(model, str) or not model.strip():
        raise LLMContractError("LLM request requires a model name.")
    if not isinstance(prompt, str) or not prompt.strip():
        raise LLMContractError("LLM request requires a non-empty prompt.")
    if not isinstance(stop, Sequence) or not stop:
        raise LLMContractError("LLM request requires stop tokens.")
    if not isinstance(request_type, str) or not request_type.strip():
        raise LLMContractError("LLM request requires a request type.")

    options = {
        "temperature": float(temperature),
        "stop": tuple(stop),
    }
    request = LLMRequest(
        model=model.strip(),
        prompt=prompt,
        options=options,
        request_type=request_type.strip(),
    )
    return {
        "model": request.model,
        "prompt": request.prompt,
        "options": request.options,
    }


def extract_response_text(response: Mapping[str, Any] | str) -> str:
    if isinstance(response, str):
        return validate_response_text(response)
    if isinstance(response, Mapping):
        if "response" not in response:
            raise LLMContractError("LLM response missing 'response' field.")
        return validate_response_text(response.get("response", ""))
    raise LLMContractError("LLM response must be a mapping or string.")


def validate_response_text(text: str) -> str:
    if not isinstance(text, str):
        raise LLMContractError("LLM response text must be a string.")
    cleaned = text.strip()
    if not cleaned:
        raise LLMContractError("LLM response text cannot be empty.")
    return cleaned


def validate_placeholder_parity(
    source_text: str,
    target_text: str,
    context: dict[str, Any] | None = None,
) -> ValidationResult:
    return validate_placeholder_order(source_text, target_text, context=context)
