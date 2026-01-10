import re
import difflib
from core.masker import Masker
from core.database import (get_cached_record, save_translation, engine,
                           TranslationRecord)
from services.llm_service import LLMService, validate_placeholders
from sqlmodel import Session, select


class TranslationEngine:
    def __init__(self, llm_service: LLMService | None):
        self.llm = llm_service
        self.masker = Masker()
        
    def run_translation(
            self,
            segments,
            target_lang,
            glossary="",
            style="",
            forbidden="",
            temp=0.1,
            strict=True,
            prompt_template="",
            glossary_dict=None,
            project_name="default"
    ):
        for i, seg in enumerate(segments):
            
            if getattr(seg, 'is_verified', False):
                continue
            # 1. Restore from DB for THIS project (optional but useful)
            record = get_cached_record(
                seg.source_text, target_lang, project_name)
            if record:
                seg.translation = record.translation
                seg.is_verified = record.is_verified 
                seg.never_translate = record.never_translate
                seg.ai_draft = record.ai_draft
                seg.thought = "Restored from Memory"

            # 2. Context
            prev_text = segments[i-1].source_text if i > 0 else ""
            context_snippet = f"PREVIOUS LINE: {prev_text}" if prev_text else ""

            # 3. Translate
            processed = self.translate_single_segment(
                seg,
                target_lang,
                project_name,
                glossary,
                style,
                forbidden,
                temp,
                strict,
                prompt_template,
                context_extra=context_snippet
            )

            success = False
            if processed and seg.translation:
                success = "[TAG ERROR]" not in seg.translation

            has_risk = False
            if processed and seg.translation:
                has_risk = self.audit_segment(seg, glossary_dict)

            if processed:
                setattr(seg, "has_risk", has_risk)

            if processed and (success or not strict):
                save_translation(
                    seg.source_text,
                    target_lang,
                    seg.translation,
                    project_name=project_name,
                    verified=seg.is_verified,
                    skip=seg.never_translate,
                    ai_draft=seg.ai_draft,
                )

    def audit_segment(self, seg, glossary_dict=None) -> bool:
        """Runs terminology and risk checks for a single segment."""
        alerts: list[str] = []

        src = seg.source_text or ""
        trn = seg.translation or ""

        # 1) Terminology – reuse audit_terminology
        if glossary_dict:
            missed = self.audit_terminology(src, trn, glossary_dict)
            if missed:
                alerts.append("Missing Terms: " + ", ".join(missed))

        # 2) Risk – reuse calculate_risk (tags + length)
        risk_msg = self.calculate_risk(src, trn)
        if risk_msg:
            alerts.append(risk_msg)

        if alerts:
            base = seg.thought or ""
            seg.thought = "⚠️ " + \
                " | ".join(alerts) + ((" | " + base) if base else "")
            return True

        return False

    def find_fuzzy_match(
        self,
        source_text: str,
        project_name: str,
        target_lang: str,
        threshold: float = 0.7
    ):
        """Searches the DB for the most similar English string within a project/lang."""
        with Session(engine) as session:
            statement = select(TranslationRecord).where(
                TranslationRecord.project_name == project_name,
                TranslationRecord.target_lang == target_lang
            )
            records = session.exec(statement).all()

            best_ratio = 0.0
            best_match = None

            for r in records:
                ratio = difflib.SequenceMatcher(
                    None,
                    source_text.lower(),
                    r.source_text.lower()
                ).ratio()

                if ratio > best_ratio:
                    best_ratio = ratio
                    best_match = r

                if best_ratio > 0.95:
                    break

            if best_match and best_ratio >= threshold:
                return {
                    "source": best_match.source_text,
                    "translation": best_match.translation,
                    "score": round(best_ratio * 100),
                }
        return None

    def calculate_risk(self, source: str, translation: str) -> str:
        """Heuristic to find lines that likely need human eyes."""
        reasons = []
        # 1. Tag Density
        tag_count = len(re.findall(r"\[#_\d+_\]", source))
        if tag_count > 3:
            reasons.append("High Tag Density")

        # 2. Length Ratio (Bulgarian is usually ~20% longer, but 100% longer is suspicious)
        if len(source) > 10:
            ratio = len(translation) / len(source)
            if ratio > 2.0 or ratio < 0.5:
                reasons.append("Length Anomaly")

        return " | ".join(reasons) if reasons else ""

    def translate_single_segment(
        self,
        seg,
        target_lang,
        project_name,
        glossary,
        style,
        forbidden,
        temp,
        strict,
        prompt_template,
        context_extra="",
        glossary_dict=None,
    ):
        # Supreme guard: never touch manually verified segments
        if getattr(seg, "is_verified", False):
            return False

        if not seg.source_text or not seg.source_text.strip():
            seg.translation = ""
            return False

        masked_text, tokens = self.masker.mask(seg.source_text)
        num_source_tags = len(tokens)

        text_without_tags = re.sub(r"\[#_\d+_\]", "", masked_text).strip()
        if not text_without_tags:
            seg.translation = self.masker.unmask(masked_text, tokens)
            return True

        clean_context = seg.translation.replace("[TAG ERROR]", "").strip()
        if self.llm is None:
            raise RuntimeError(
                "TranslationEngine.translate_single_segment called without an LLMService instance"
            )

        raw_translation, thought = self.llm.translate_segment(
            text=masked_text,
            target_lang=target_lang,
            project_name=project_name,
            glossary=glossary,
            style=style,
            forbidden=forbidden,
            temp=temp,
            prompt_template=prompt_template,
            current_translation=clean_context,
            context_extra=context_extra,
        )

        success = validate_placeholders(masked_text, raw_translation)
        final_text = self.masker.unmask(raw_translation, tokens)

        if not getattr(seg, "ai_draft", ""):
            seg.ai_draft = final_text

        if num_source_tags == 0:
            final_text = re.sub(r"\[#_\d+_\]", "", final_text).strip()
            success = True

        if not success and num_source_tags > 0 and strict:
            final_text = f"[TAG ERROR] {final_text}"

        if seg.source_text.isupper() and any(c.isalpha() for c in seg.source_text):
            final_text = final_text.upper()

        seg.translation = final_text
        seg.thought = thought

        if not getattr(seg, "ai_draft", ""):
            seg.ai_draft = final_text

        return True

    def audit_terminology(self, source: str, translation: str, glossary: dict) -> list:
        """Language-agnostic check for glossary terms."""
        missed = []
        s_low = source.lower()
        t_low = translation.lower()

        for en_term, target_term in glossary.items():
            if en_term in s_low:
                # In most languages (BG, DE, FR), the root of the word stays 
                # similar even with different endings.
                if target_term not in t_low:
                    # We only flag if the term is completely missing.
                    # This reduces false positives for grammar endings.
                    missed.append(f"{en_term} -> {target_term}")
        return missed
