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
            models_list = getattr(response, 'models', response.get('models', []))
            return [getattr(m, 'model', m.get('name', 'unknown')) for m in models_list]
        except:
            return ["ollama-not-found"]

    def translate_segment(self, text, target_lang, glossary, style, forbidden, temp, prompt_template, current_translation=""):
        """Uses a custom prompt template provided by the UI."""
        
        # 1. Prepare the Prompt
        if not prompt_template or "{source}" not in prompt_template:
            prompt_template = "Translate to {target_lang}: {source}"

        full_prompt = prompt_template.replace("{source}", text)\
                                     .replace("{target_lang}", target_lang)\
                                     .replace("{glossary}", glossary)\
                                     .replace("{style}", style)\
                                     .replace("{forbidden}", forbidden)\
                                     .replace("{translation}", current_translation)

        try:
            # 2. Call the AI
            response = ollama.generate(
                model=self.model,
                prompt=full_prompt,
                options={
                    "temperature": temp,
                    "stop": ["###", "SOURCE:", "FIXED:", "TARGET:", "\n\n\n"]
                }
            )
            raw = response['response'].strip()
                       
            # 3. ANTI-CHEAT: Remove Chinese characters (CJK Unified Ideographs)
            # This is where we stop Qwen from being a cheater.
            raw = re.sub(r'[一-龥]', '', raw) 

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
                lines = [l.strip() for l in translation.split("\n") if l.strip()]
                if lines:
                    translation = lines[-1]

            return translation.strip(), thought
            
        except Exception as e:
            return f"Error: {str(e)}", ""
        
        