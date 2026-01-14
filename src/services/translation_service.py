from __future__ import annotations

from core.engine import TranslationEngine
from services.llm_service import LLMService


def run_batch_translation(
    segments,
    target_lang: str,
    llm_service: LLMService,
    glossary: str = "",
    style: str = "",
    forbidden: str = "",
    temp: float = 0.1,
    strict: bool = True,
    prompt_template: str = "",
    glossary_dict=None,
    project_name: str = "default",
    progress_callback=None,
    should_stop=None,
) -> None:
    engine = TranslationEngine(llm_service)
    engine.run_translation(
        segments,
        target_lang,
        glossary=glossary,
        style=style,
        forbidden=forbidden,
        temp=temp,
        strict=strict,
        prompt_template=prompt_template,
        glossary_dict=glossary_dict,
        project_name=project_name,
        progress_callback=progress_callback,
        should_stop=should_stop,
    )
