import ollama
import re


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
            return ["ollama-not-found"]

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
        # 1. Fallback if template is empty
        if not prompt_template or "{source}" not in prompt_template:
            prompt_template = (
                "### ROLE: Localizer\n### "
                "CONTEXT: {context}\n### "
                "SOURCE: {source}\n### "
                "TARGET ({target_lang}):"
            )

        # 2. Injection logic
        # We use .replace instead of .format to avoid errors with stray {} in AI text
        full_prompt = prompt_template.replace("{source}", text)\
                                     .replace("{target_lang}", target_lang)\
                                     .replace("{project_name}", project_name)\
                                     .replace("{glossary}", glossary)\
                                     .replace("{style}", style)\
                                     .replace("{forbidden}", forbidden)\
                                     .replace("{translation}", current_translation)\
                                     .replace("{context}", context_extra)

        if context_extra and "{context}" not in prompt_template:
            full_prompt = f"### CONTEXT: {context_extra}\n" + full_prompt

        # DEBUG: Let's see what the AI is actually reading
        # print("-" * 30)
        # print(f"SENDING PROMPT:\n{full_prompt}")
        # print("-" * 30)

        try:
            response = ollama.generate(
                model=self.model,
                prompt=full_prompt,
                options={
                    "temperature": float(temp),
                    "stop": ["###", "SOURCE:", "FIXED:", "TARGET:", "\n\n\n", "Certainly", "Sure"]
                }
            )
            raw = response['response'].strip()

            # --- CLEANUP: The 'Politeness' Filter ---
            # List of phrases that often precede the actual translation
            polite_junk = [
                "Certainly", "Sure", "Here is", "I have fixed", 
                "Let's correct", "Разбира се", "Ето превода", 
                "Certainly!", "Sure!", "I can help"
            ]
            
            # 1. If the result is multiple lines, the last line is usually the translation
            if "\n" in raw:
                lines = [l.strip() for l in raw.split("\n") if l.strip()]
                # Check if the first line starts with any junk phrase
                if any(lines[0].startswith(j) for j in polite_junk):
                    raw = lines[-1] # Take the last line as the actual translation
            for j in polite_junk:
                if raw.startswith(j):
                    raw = raw.replace(j, "", 1).strip()
                    if raw.startswith("!") or raw.startswith(":"):
                        raw = raw[1:].strip()

            # 2. Final check: if the result starts with "Certainly" or "Sure", 
            # we strip until the first bracket [#_ or the first Cyrillic letter
            if raw.startswith(("Sure", "Certain", "Here")):
                # Find the first occurrence of [# or a Bulgarian letter and slice from there
                match = re.search(r'\[#|[А-Яа-я]', raw)
                if match:
                    raw = raw[match.start():]

            # 4. Extract thinking tags (DeepSeek/Reasoning models)
            thought = ""
            translation = raw
            if "<think>" in raw:
                try:
                    parts = raw.split("</think>")
                    thought = parts[0].replace("<think>", "").strip()
                    translation = parts[1].strip()
                except:
                    pass

            # 5. FINAL POLISH: If there are multiple lines, take the very last one.
            # (Helps when the AI repeats the instructions or adds preamble)
            if "\n" in translation:
                # We filter out empty lines and take the last piece of text
                lines = [l.strip()
                         for l in translation.split("\n") if l.strip()]
                if lines:
                    translation = lines[-1]

            return translation.strip(), thought

        except Exception as e:
            return f"Error: {str(e)}", ""
