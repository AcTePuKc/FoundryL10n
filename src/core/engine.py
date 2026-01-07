import re
from core.masker import Masker
from core.database import get_cached_record, save_translation
from services.llm_service import validate_placeholders

class TranslationEngine:
    def __init__(self, llm_service):
        self.masker = Masker()
        self.llm = llm_service

    def run_translation(self, segments, target_lang, glossary="", style="", forbidden="", temp=0.1, strict=True, prompt_template=""):
        for seg in segments:
            record = get_cached_record(seg.source_text, target_lang)
            cached_translation = ""
            has_valid_cache = False

            if record:
                cached_translation = record.translation or ""
                has_valid_cache = bool(cached_translation and "[TAG ERROR]" not in cached_translation)

                if record.is_verified or record.never_translate:
                    if has_valid_cache:
                        seg.translation = cached_translation
                    seg.thought = "Verified in Memory (Skipped)" if record.is_verified else "Never Translate (Skipped)"
                    continue

                if has_valid_cache and (not seg.translation or "[TAG ERROR]" in seg.translation):
                    seg.translation = cached_translation
                    seg.thought = "Cached result"
                    continue

            if seg.translation and "[TAG ERROR]" not in seg.translation:
                if not has_valid_cache:
                    save_translation(seg.source_text, target_lang, seg.translation)
                continue

            self.translate_single_segment(seg, target_lang, glossary, style, forbidden, temp, strict, prompt_template)


    def translate_single_segment(self, seg, target_lang, glossary, style, forbidden, temp, strict, prompt_template):
        if not seg.source_text or not seg.source_text.strip():
            seg.translation = ""
            return

        masked_text, tokens = self.masker.mask(seg.source_text)
        num_source_tags = len(tokens)
        
        # Tag-only check
        text_without_tags = re.sub(r"\[#_\d+_\]", "", masked_text).strip()
        if not text_without_tags:
            seg.translation = self.masker.unmask(masked_text, tokens)
            return

        clean_context = seg.translation.replace("[TAG ERROR]", "").strip()
        
        # Simple Retry Loop
        raw_translation, thought = self.llm.translate_segment(
            masked_text, target_lang, glossary, style, forbidden, temp, prompt_template, current_translation=clean_context
        )
        
        success = validate_placeholders(masked_text, raw_translation)
        final_text = self.masker.unmask(raw_translation, tokens)
        
        # Hallucination Guard
        if num_source_tags == 0:
            final_text = re.sub(r"\[#_\d+_\]", "", final_text).strip()
            success = True
        
        if not success and num_source_tags > 0:
            if strict: 
                final_text = f"[TAG ERROR] {final_text}"
        
        # Case Force
        if seg.source_text.isupper() and any(c.isalpha() for c in seg.source_text):
            final_text = final_text.upper()

        seg.translation = final_text
        seg.thought = thought
        
        if success or not strict:
            save_translation(seg.source_text, target_lang, seg.translation)