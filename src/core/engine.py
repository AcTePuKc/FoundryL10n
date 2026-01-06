import re
from core.masker import Masker
from core.database import get_cached_translation, save_translation
from services.llm_service import validate_placeholders

class TranslationEngine:
    def __init__(self, llm_service):
        self.masker = Masker()
        self.llm = llm_service

    def run_translation(self, segments, target_lang, glossary="", style="", forbidden="", temp=0.1, strict=True, prompt_template=""):
        """The core orchestration loop for translating segments."""
        for seg in segments:
            # --- 1. SUCCESS GUARD (The Pass-2 Optimizer) ---
            # If the row already has a translation and NO tag error, skip it entirely.
            # This allows you to run Pass 2 only on the rows that failed.
            if seg.translation and "[TAG ERROR]" not in seg.translation:
                # We don't change the thought so the UI keeps the old one
                continue

            # --- 2. EMPTY ROW GUARD ---
            if not seg.source_text or not seg.source_text.strip():
                seg.translation = ""
                seg.thought = "Skipped: Empty source text."
                continue

            # --- 3. CACHE CHECK (Memory) ---
            # Only check memory if the translation cell is empty.
            if not seg.translation:
                cached = get_cached_translation(seg.source_text, target_lang)
                if cached:
                    seg.translation = cached
                    seg.thought = "Restored from local memory (DB)."
                    continue
            
            # --- 4. MASKING ---
            masked_text, tokens = self.masker.mask(seg.source_text)
            num_source_tags = len(tokens)

            # --- 5. TAG-ONLY GUARD ---
            text_without_tags = re.sub(r"\[#_\d+_\]", "", masked_text).strip()
            if not text_without_tags:
                seg.translation = self.masker.unmask(masked_text, tokens)
                seg.thought = "Skipped: Tag-only source."
                continue
            
            # --- 6. CONTEXT PREPARATION ---
            clean_context = ""
            if seg.translation:
                clean_context = seg.translation.replace("[TAG ERROR]", "").strip()

            # --- 7. LLM TRANSLATION WITH RETRIES ---
            max_attempts = 2 if (strict and num_source_tags > 0) else 1 
            raw_translation = ""
            thought = ""
            success = False

            for attempt in range(max_attempts):
                current_temp = temp if attempt == 0 else 0.0
                
                raw_translation, thought = self.llm.translate_segment(
                    masked_text,
                    target_lang,
                    glossary,
                    style,
                    forbidden,
                    current_temp,
                    prompt_template,
                    current_translation=clean_context
                )
                
                if validate_placeholders(masked_text, raw_translation):
                    success = True
                    break 

            # --- 8. POST-PROCESS & HALLUCINATION GUARD ---
            seg.thought = thought
            
            # Unmask the result
            final_text = self.masker.unmask(raw_translation, tokens)
            
            # HALLUCINATION GUARD: If source had 0 tags, AI is NOT allowed to invent any.
            # This fixes headers like 'STOLEN ART DISCOVERED' getting junk tags.
            if num_source_tags == 0:
                final_text = re.sub(r"\[#_\d+_\]", "", final_text).strip()
                # If we stripped hallucinations, we treat this as a success
                success = True
                        
            if not success and num_source_tags > 0:
                if strict:
                    final_text = f"[TAG ERROR] {final_text}"
                    seg.thought += " | CRITICAL: Tag Mismatch. Not saved to DB."
                else:
                    seg.thought += " | WARNING: Tag Mismatch. Saved anyway (Strict OFF)."

            # --- 9. ALLCAPS FORCE ---
            has_letters = any(char.isalpha() for char in seg.source_text)
            if has_letters and seg.source_text.isupper():
                final_text = final_text.upper()
            
            seg.translation = final_text
            
            # --- 10. SAVE TO MEMORY ---
            if success or not strict:
                save_translation(seg.source_text, target_lang, seg.translation)

    @staticmethod
    def reinject_tags(masked_source: str, translated: str) -> str:
        """Heuristic to append missing tags to the end of a translation."""
        tag_pattern = r"\[TAG_\d+\]"
        src_tags = re.findall(tag_pattern, masked_source)
        out_tags = re.findall(tag_pattern, translated)

        # If the LLM hallucinated extra tags, this logic might be risky, so we return as-is
        if len(out_tags) > len(src_tags):
            return translated

        result = translated
        # Find tags that are in source but missing in output
        missing = [t for t in src_tags if t not in out_tags]
        
        if missing:
            # Append missing tags to the end so validation passes
            result = result.rstrip() + " " + " ".join(missing)

        return result