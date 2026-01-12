import ollama
import re

from core.i18n import I18N

DEFAULT_MODEL_UNAVAILABLE = "llm_model_unavailable"
CONTEXT_PREFIX = "### CONTEXT: {context}\n"
POLITE_JUNK = (
    "Certainly", "Sure", "Here is",
    "I have fixed", "Let's correct",
    "Разбира се", "Ето превода", "Ето и превода"
)
STOP_TOKENS = ["###", "SOURCE:", "FIXED:", "TARGET:", "\n\n\n"]

def validate_placeholders(original: str, translated: str) -> bool:
    # Matches [#_0_], [#_1_], etc.
    pattern = r"\[#_\d+_\]"
    orig_tags = re.findall(pattern, original)
    trans_tags = re.findall(pattern, translated)
    return len(orig_tags) == len(trans_tags)


class LLMService:
    def __init__(self, model_name="qwen2.5:7b"):
        self.model = model_name

    def get_models(self):
        try:
            response = ollama.list()
            models_list = getattr(response, 'models',
                                  response.get('models', []))
            return [getattr(m, 'model', m.get('name', 'unknown')) for m in models_list]
        except:
            return [I18N.t(DEFAULT_MODEL_UNAVAILABLE)]

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
            context_extra=""
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
            response = ollama.generate(
                model=self.model,
                prompt=full_prompt,
                options={
                    "temperature": float(temp),
                    "stop": STOP_TOKENS
                }
            )
            raw = response['response'].strip()

            # 2. EXTRACT THINKING (Do this first to get the pure text)
            thought = ""
            translation = raw
            if "<think>" in raw:
                try:
                    parts = raw.split("</think>")
                    thought = parts[0].replace("<think>", "").strip()
                    translation = parts[1].strip()
                except Exception:
                    pass

            # 3. FIND THE BEST LINE (The 'Needle in the Haystack')
            # If the AI chatted, the translation is usually the line with tags or Cyrillic
            if "\n" in translation:
                lines = [l.strip()
                         for l in translation.split("\n") if l.strip()]
                best_line = lines[-1]  # Default to the last line
                for line in lines:
                    # If this line contains a Tag [#_ or Bulgarian letters, it's our winner
                    if re.search(r'\[#_\d+_\]|[А-Яа-я]', line):
                        best_line = line
                        break
                translation = best_line

            # 4. STRIP POLITE JUNK (safe)
            cleaned = translation
            for junk in POLITE_JUNK:
                if cleaned.lower().startswith(junk.lower()):
                    candidate = cleaned[len(junk):].strip().lstrip(":! ")
                    if candidate:
                        cleaned = candidate

            translation = cleaned

            # 5. ANTI-CHEAT (CJK-safe)
            lang_upper = target_lang.upper()
            is_cjk = any(x in lang_upper for x in (
                "JA", "JP", "ZH", "CH", "KO", "KR"))

            if not is_cjk:
                translation = re.sub(r'[一-龥]|[ぁ-ん]|[ァ-ン]', '', translation)

            return translation.strip(), thought

        except Exception as e:
            return I18N.t("llm_error").format(error=str(e)), ""
