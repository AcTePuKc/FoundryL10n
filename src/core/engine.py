import re
import difflib
from core.masker import Masker
from core.rlm_segmenter import RLMSegmenter
from core.rlm_validator import validate_placeholder_order, validate_segments
from core.database import (get_cached_record, save_translation, engine,
                           TranslationRecord)
from core.i18n import I18N
from services.llm_service import LLMService
from sqlmodel import Session, select, col


class TranslationEngine:
    def __init__(self, llm_service: LLMService | None):
        self.llm = llm_service
        self.masker = Masker()
        self.segmenter = RLMSegmenter()

    def _segment_is_remote(self, seg) -> bool:
        row = getattr(seg, "original_row", {}) or {}
        return bool(
            getattr(seg, "provider_id", None)
            or getattr(seg, "remote_id", None)
            or row.get("provider_id")
            or row.get("remote_id")
        )
        
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
            project_name="default",
            progress_callback=None,
            should_stop=None,
    ):
        for i, seg in enumerate(segments):
            if should_stop is not None and should_stop():
                break
            
            is_verified = getattr(seg, 'is_verified', False)
            is_skip = getattr(seg, 'never_translate', False)

            if is_verified or is_skip:
                continue
            # 1. Restore from DB for THIS project (optional but useful)
            record = get_cached_record(
                seg.source_text,
                target_lang,
                project_name,
                segment_key=seg.key,
            )
            if record:
                seg.translation = record.translation
                seg.is_verified = record.is_verified 
                seg.never_translate = record.never_translate
                seg.ai_draft = record.ai_draft
                seg.thought = I18N.t("thought_restored_from_memory")

            # 2. IMPROVED CONTEXT: Previous + Next Line
            prev_text = segments[i-1].source_text if i > 0 else ""
            next_text = segments[i+1].source_text if i < len(segments)-1 else ""
            
            context_bits = []
            if prev_text: 
                context_bits.append(f"PREVIOUS: {prev_text}")
            if next_text: 
                context_bits.append(f"NEXT: {next_text}")
            
            context_snippet = "\n".join(context_bits)

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

            if processed and success:
                save_translation(
                    seg.source_text,
                    target_lang,
                    seg.translation,
                    project_name=project_name,
                    segment_key=seg.key,
                    verified=seg.is_verified,
                    skip=seg.never_translate,
                    ai_draft=seg.ai_draft,
                )
            if progress_callback is not None:
                progress_callback(i + 1)
    
    def run_pseudo_localization(self, segments):
        """Turns all untranslated rows into expanded 'Fake' text for font testing."""
        for seg in segments:
            if seg.is_verified or seg.translation:
                continue
            
            # Simple expansion and wrapping
            # [!! Text becomes longér !!]
            source = seg.source_text
            # Replace some letters with accented ones to test font support
            pseudo = source.replace("a", "á").replace("e", "é").replace("o", "ó").replace("i", "í")
            seg.translation = f"[!! {pseudo} !!]"
            seg.thought = I18N.t("thought_pseudo_localization_pass")

    def audit_segment(self, seg, glossary_dict=None) -> bool:
        """Runs terminology and risk checks for a single segment."""
        alerts: list[str] = []

        src = seg.source_text or ""
        trn = seg.translation or ""

        # 1) Terminology – reuse audit_terminology
        if glossary_dict:
            missed = self.audit_terminology(src, trn, glossary_dict)
            if missed:
                alerts.append(
                    I18N.t("audit_missing_terms").format(terms=", ".join(missed))
                )

        # 2) Risk – reuse calculate_risk (tags + length)
        risk_msg = self.calculate_risk(src, trn)
        if risk_msg:
            alerts.append(risk_msg)

        if alerts:
            base = seg.thought or ""
            if base.startswith("⚠️ "):
                base = base[len("⚠️ "):]
            seg.thought = "⚠️ " + " | ".join(alerts) + ((" | " + base) if base else "")
            return True

        return False

    def find_fuzzy_match(
            self, 
            source_text: str, 
            project_name: str, 
            target_lang: str, 
            threshold=0.7
            ):
        """Searches the DB for the most similar string with optimized performance."""
        with Session(engine) as session:
            # Use col() to satisfy Pylance for .desc()
            statement = select(TranslationRecord).where(
                col(TranslationRecord.project_name) == project_name,
                col(TranslationRecord.target_lang) == target_lang
            ).order_by(col(TranslationRecord.id).desc()).limit(2000)
            
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
        masked_source, _ = self.masker.mask(source)
        tag_count = len(re.findall(r"@@\s*PLACEHOLDER_\d+\s*@@", masked_source))
        if tag_count > 3:
            reasons.append(I18N.t("audit_high_tag_density"))

        # 2. Length Ratio (Bulgarian is usually ~20% longer, but 100% longer is suspicious)
        if len(source) > 10:
            ratio = len(translation) / len(source)
            if ratio > 2.0 or ratio < 0.5:
                reasons.append(I18N.t("audit_length_anomaly"))

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

        seg.repair_attempted = False
        seg.repair_success = False
        seg.repair_failed = False

        if not seg.source_text or not seg.source_text.strip():
            seg.translation = ""
            return False

        masked_text, tokens = self.masker.mask(seg.source_text)
        num_source_tags = len(tokens)

        source_segment_result = self.segmenter.segment(
            raw_line=seg.source_text,
            masked_line=masked_text,
            context={"segment_id": getattr(seg, "key", None)},
        )
        text_segments = [segment for segment in source_segment_result.segments if segment.kind == "text"]
        if not text_segments:
            seg.translation = self.masker.unmask(masked_text, tokens)
            return True

        clean_context = seg.translation.replace("[TAG ERROR]", "").strip()
        if self.llm is None:
            raise RuntimeError(
                "TranslationEngine.translate_single_segment called without an LLMService instance"
            )

        if self._segment_is_remote(seg):
            remote_context_bits = []
            if seg.source_text:
                remote_context_bits.append(f"REMOTE SOURCE: {seg.source_text}")
            if clean_context:
                remote_context_bits.append(f"REMOTE TARGET: {clean_context}")
            if remote_context_bits:
                remote_context = "\n".join(remote_context_bits)
                context_extra = (
                    f"{remote_context}\n{context_extra}".strip()
                    if context_extra
                    else remote_context
                )

        translated_texts: list[str] = []
        thoughts: list[str] = []
        for segment in text_segments:
            if not segment.value.strip():
                translated_texts.append(segment.value)
                continue
            raw_translation, thought = self.llm.translate_segment(
                text=segment.value,
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
            translated_texts.append(raw_translation)
            if thought:
                thoughts.append(thought)

        translated_iter = iter(translated_texts)
        candidate_segments = []
        for segment in source_segment_result.segments:
            if segment.kind == "text":
                candidate_segments.append(next(translated_iter, ""))
            else:
                candidate_segments.append(segment.value)
        candidate_text = "".join(candidate_segments)
        final_text = self.masker.unmask(candidate_text, tokens)

        target_segment_result = self.segmenter.segment(
            raw_line=candidate_text,
            masked_line=candidate_text,
            context={"segment_id": getattr(seg, "key", None)},
        )
        validation = validate_segments(
            source_segments=source_segment_result.segments,
            target_segments=target_segment_result.segments,
            source_tags=source_segment_result.tags,
            target_tags=target_segment_result.tags,
            context={"segment_id": getattr(seg, "key", None)},
        )
        placeholder_validation = validate_placeholder_order(
            seg.source_text,
            final_text,
            context={"segment_id": getattr(seg, "key", None)},
        )
        success = validation.is_valid and placeholder_validation.is_valid
        manual_review_message = ""

        if not success and num_source_tags > 0:
            seg.repair_attempted = True
            repaired_text, repair_thought = self.llm.repair_placeholders(
                source_line=seg.source_text,
                candidate_translation=final_text,
                expected_placeholders=tokens,
            )
            if repaired_text:
                repaired_masked, _ = self.masker.mask(repaired_text)
                repaired_target_result = self.segmenter.segment(
                    raw_line=repaired_masked,
                    masked_line=repaired_masked,
                    context={"segment_id": getattr(seg, "key", None)},
                )
                repaired_validation = validate_segments(
                    source_segments=source_segment_result.segments,
                    target_segments=repaired_target_result.segments,
                    source_tags=source_segment_result.tags,
                    target_tags=repaired_target_result.tags,
                    context={"segment_id": getattr(seg, "key", None)},
                )
                placeholder_validation = validate_placeholder_order(
                    seg.source_text,
                    repaired_text,
                    context={"segment_id": getattr(seg, "key", None)},
                )
                success = repaired_validation.is_valid and placeholder_validation.is_valid
                final_text = repaired_text
                if repair_thought:
                    thoughts.append(repair_thought)
            if success:
                seg.repair_success = True
            else:
                seg.repair_failed = True
                manual_review_message = I18N.t("audit_placeholder_manual_review")

        if not getattr(seg, "ai_draft", ""):
            seg.ai_draft = final_text

        if num_source_tags == 0:
            final_text = re.sub(r"@@\s*PLACEHOLDER_\d+\s*@@", "", final_text).strip()

        if not success and not manual_review_message:
            manual_review_message = I18N.t("audit_placeholder_manual_review")

        if not success:
            final_text = f"[TAG ERROR] {final_text}"

        if seg.source_text.isupper() and any(c.isalpha() for c in seg.source_text):
            final_text = final_text.upper()

        seg.translation = final_text
        seg.thought = " | ".join(thoughts)
        if manual_review_message:
            thought_parts = [f"⚠️ {manual_review_message}"]
            if seg.thought:
                thought_parts.append(seg.thought)
            seg.thought = " | ".join(thought_parts)

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
