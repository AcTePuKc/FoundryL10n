import ollama
import re
import httpx

from core.i18n import I18N

DEFAULT_MODEL_UNAVAILABLE = "llm_model_unavailable"
CONTEXT_PREFIX = "### CONTEXT: {context}\n"
POLITE_JUNK = (
    "Certainly", "Sure", "Here is",
    "I have fixed", "Let's correct",
    "Разбира се", "Ето превода", "Ето и превода",
    "Ето коригирания превод", "Коригиран превод"
)
LABEL_PREFIXES = (
    "Here is", "I have fixed", "Let's correct",
    "Ето превода", "Ето и превода",
    "Ето коригирания превод", "Коригиран превод"
)
SOURCE_POLITE_MAP = {
    "sure is": "разбира се",
    "sure": "разбира се",
    "certainly": "разбира се",
}
STOP_TOKENS = ("###", "SOURCE:", "FIXED:", "TARGET:", "\n\n\n")
LABEL_ONLY_PATTERNS = (
    re.compile(r"^Ето .*превод[:：]?$", re.IGNORECASE),
    re.compile(r"^CORRECTED TRANSLATION[:：]?$", re.IGNORECASE),
)
PLACEHOLDER_PATTERN = r"@@\s*PLACEHOLDER_\d+\s*@@"
TAG_OR_PLACEHOLDER_PATTERN = re.compile(rf"{PLACEHOLDER_PATTERN}|<[^>]+>")
REPAIR_PROMPT = (
    "You are a localization repair assistant. Fix placeholder placement only.\n"
    "Do not rewrite translated words. Do not add commentary.\n\n"
    "SOURCE: {source_line}\n"
    "CANDIDATE: {candidate_translation}\n"
    "EXPECTED PLACEHOLDERS (in order): {expected_placeholders}\n\n"
    "Return only the corrected translation."
)


def validate_placeholders(original: str, translated: str) -> bool:
    # Matches @@PLACEHOLDER_0@@, @@PLACEHOLDER_1@@, etc.
    orig_tags = re.findall(PLACEHOLDER_PATTERN, original)
    trans_tags = re.findall(PLACEHOLDER_PATTERN, translated)
    return len(orig_tags) == len(trans_tags)


class LLMService:
    def __init__(self, model_name="qwen2.5:7b", timeout: float | None = None):
        self.model = model_name
        self.timeout = self._normalize_timeout(timeout)
        self.client = ollama.Client(timeout=self.timeout)

    @staticmethod
    def _normalize_timeout(timeout: float | None) -> float | None:
        if timeout is None:
            return None
        try:
            value = float(timeout)
        except (TypeError, ValueError):
            return None
        if value <= 0:
            return None
        return value

    def check_connection(self):
        try:
            self.client.list()
            return True, None
        except Exception as exc:
            return False, str(exc)

    def get_models(self):
        try:
            response = self.client.list()
            models_list = getattr(response, 'models',
                                  response.get('models', []))
            return [getattr(m, 'model', m.get('name', 'unknown')) for m in models_list]
        except:
            return [I18N.t(DEFAULT_MODEL_UNAVAILABLE)]

    def _postprocess_output(self, raw: str, source_text: str, target_lang: str) -> tuple[str, str]:
        thought = ""
        translation = raw
        if "<think>" in raw:
            try:
                parts = raw.split("</think>")
                thought = parts[0].replace("<think>", "").strip()
                translation = parts[1].strip()
            except Exception:
                pass

        if "\n" in translation:
            lines = [l.strip() for l in translation.split("\n") if l.strip()]
            non_label_lines = [
                line for line in lines
                if not any(pattern.match(line) for pattern in LABEL_ONLY_PATTERNS)
            ]
            candidates = non_label_lines or lines
            best_score = None
            best_line = candidates[-1]
            for idx, line in enumerate(candidates):
                has_placeholder = bool(TAG_OR_PLACEHOLDER_PATTERN.search(line))
                token_count = len(line.split())
                score = (has_placeholder, token_count, idx)
                if best_score is None or score > best_score:
                    best_score = score
                    best_line = line
            translation = best_line

        source_lower = source_text.strip().lower()
        output_has_label_prefix = any(
            translation.lower().startswith(prefix.lower())
            for prefix in LABEL_PREFIXES
        )
        source_polite_target = None
        for source_prefix, target_prefix in SOURCE_POLITE_MAP.items():
            if source_lower.startswith(source_prefix):
                source_polite_target = target_prefix
                break

        cleaned = translation
        for junk in POLITE_JUNK:
            if cleaned.lower().startswith(junk.lower()):
                if (
                    source_polite_target is not None
                    and junk.lower() == source_polite_target
                    and not output_has_label_prefix
                ):
                    continue
                candidate = cleaned[len(junk):].strip().lstrip(":! ")
                if candidate:
                    cleaned = candidate

        translation = cleaned

        lang_upper = target_lang.upper()
        is_cjk = any(x in lang_upper for x in (
            "JA", "JP", "ZH", "CH", "KO", "KR"))

        if not is_cjk:
            translation = re.sub(r'[一-龥]|[ぁ-ん]|[ァ-ン]', '', translation)

        return translation.strip(), thought

    def translate_segment(
        self,
        text,
        target_lang,
        project_name="default",
        glossary="",
        style="",
        forbidden="",
        temp=0.1,
        prompt_template="",
        current_translation="",
        context_extra="",
    ):
        # 1. Fallback & Formatting
        if not prompt_template or "{source}" not in prompt_template:
            prompt_template = I18N.t("prompt_template_fallback")

        full_prompt = prompt_template.replace("{source}", text)\
                                     .replace("{target_lang}", target_lang)\
                                     .replace("{project_name}", project_name)\
                                     .replace("{glossary}", glossary)\
                                     .replace("{style}", style)\
                                     .replace("{forbidden}", forbidden)\
                                     .replace("{translation}", current_translation)\
                                     .replace("{context}", context_extra)

        if context_extra and "{context}" not in prompt_template:
            full_prompt = CONTEXT_PREFIX.format(context=context_extra) + full_prompt

        try:
            response = self.client.generate(
                model=self.model,
                prompt=full_prompt,
                options={
                    "temperature": float(temp),
                    "stop": STOP_TOKENS
                }
            )
            raw = response['response'].strip()
            return self._postprocess_output(raw, text, target_lang)

        except (httpx.TimeoutException, TimeoutError) as e:
            if self.timeout is not None:
                warning = I18N.t("log_llm_timeout").format(seconds=self.timeout)
            else:
                warning = I18N.t("log_llm_timeout_default")
            return f"[TAG ERROR] {I18N.t('llm_error').format(error=str(e))}", warning
        except Exception as e:
            return f"[TAG ERROR] {I18N.t('llm_error').format(error=str(e))}", ""

    @staticmethod
    def _postprocess_repair_output(raw: str) -> str:
        cleaned = raw.strip()
        if "\n" in cleaned:
            cleaned = [line.strip() for line in cleaned.split("\n") if line.strip()][-1]
        for junk in POLITE_JUNK:
            if cleaned.lower().startswith(junk.lower()):
                candidate = cleaned[len(junk):].strip().lstrip(":! ")
                if candidate:
                    cleaned = candidate
        return cleaned

    def repair_placeholders(
        self,
        source_line: str,
        candidate_translation: str,
        expected_placeholders: list[str],
    ) -> tuple[str | None, str]:
        expected_text = ", ".join(expected_placeholders)
        prompt = REPAIR_PROMPT.format(
            source_line=source_line,
            candidate_translation=candidate_translation,
            expected_placeholders=expected_text or "[]",
        )
        try:
            response = self.client.generate(
                model=self.model,
                prompt=prompt,
                options={
                    "temperature": 0.0,
                    "stop": STOP_TOKENS,
                },
            )
            raw = response["response"].strip()
            return self._postprocess_repair_output(raw), ""
        except (httpx.TimeoutException, TimeoutError) as e:
            if self.timeout is not None:
                warning = I18N.t("log_llm_timeout").format(seconds=self.timeout)
            else:
                warning = I18N.t("log_llm_timeout_default")
            return None, warning
        except Exception as e:
            return None, I18N.t("llm_error").format(error=str(e))
