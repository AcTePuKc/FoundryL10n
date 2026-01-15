from pathlib import Path

from PySide6.QtCore import QThread, Signal
from core.engine import TranslationEngine
from core.translation_pipeline import run_ordered_jsonl_pipeline, segment_to_jsonl_entry
from services.resource_service import ResourceLoader
from services.translation_service import run_batch_translation


class TranslationWorker(QThread):
    progress_signal = Signal(int)
    finished_signal = Signal(list)
    def __init__(
        self,
        segments,
        target_lang,
        llm_service,
        glossary_path,
        style_path,
        forbidden_path,
        temp=0.1,
        prompt_template="",
        strict=True,
        project_name: str = "default",
        parent=None,
    ):
        super().__init__(parent)
        self.segments = segments
        self.target_lang = target_lang
        self.llm_service = llm_service
        self.glossary_path = glossary_path
        self.style_path = style_path
        self.forbidden_path = forbidden_path
        self.temp = temp
        self.prompt_template = prompt_template
        self.strict = strict
        self.project_name = project_name

        self._is_running = True


    def stop(self):
        """Method to safely interrupt the loop."""
        self._is_running = False

    def run(self):
        loader = ResourceLoader()

        # 1. Load resources (String versions for LLM)
        glossary_text = loader.load_glossary(self.glossary_path)
        style_content = loader.load_style_guide(self.style_path)
        forbidden_content = loader.load_forbidden_words(self.forbidden_path)

        # 2. Load Dictionary version for the local Audit
        glossary_dict = loader.load_glossary_dict(self.glossary_path)

        def should_stop() -> bool:
            return not self._is_running

        run_batch_translation(
            self.segments,
            self.target_lang,
            self.llm_service,
            glossary=glossary_text,
            style=style_content,
            forbidden=forbidden_content,
            temp=self.temp,
            strict=self.strict,
            prompt_template=self.prompt_template,
            glossary_dict=glossary_dict,
            project_name=self.project_name,
            progress_callback=self.progress_signal.emit,
            should_stop=should_stop,
        )

        self.finished_signal.emit(self.segments)


class JSONLPipelineWorker(QThread):
    progress_signal = Signal(int)
    finished_signal = Signal(list)

    def __init__(
        self,
        segments,
        target_lang,
        llm_service,
        glossary_path,
        style_path,
        forbidden_path,
        output_path: Path,
        chunk_size: int = 20,
        temp=0.1,
        prompt_template="",
        strict=True,
        project_name: str = "default",
        parent=None,
    ):
        super().__init__(parent)
        self.segments = segments
        self.target_lang = target_lang
        self.llm_service = llm_service
        self.glossary_path = glossary_path
        self.style_path = style_path
        self.forbidden_path = forbidden_path
        self.output_path = output_path
        self.chunk_size = chunk_size
        self.temp = temp
        self.prompt_template = prompt_template
        self.strict = strict
        self.project_name = project_name
        self._is_running = True

    def stop(self):
        """Method to safely interrupt the loop."""
        self._is_running = False

    def run(self):
        loader = ResourceLoader()

        glossary_text = loader.load_glossary(self.glossary_path)
        style_content = loader.load_style_guide(self.style_path)
        forbidden_content = loader.load_forbidden_words(self.forbidden_path)
        glossary_dict = loader.load_glossary_dict(self.glossary_path)

        engine = TranslationEngine(self.llm_service)
        segments_by_key = {seg.key: seg for seg in self.segments}

        def process_chunk(entries):
            processed_entries = []
            for entry in entries:
                if not self._is_running:
                    processed_entries.append(entry)
                    continue
                key = str(entry.payload.get("key") or "")
                seg = segments_by_key.get(key)
                if seg is None:
                    processed_entries.append(entry)
                    continue
                engine.process_segment(
                    segments=self.segments,
                    index=entry.order,
                    target_lang=self.target_lang,
                    glossary=glossary_text,
                    style=style_content,
                    forbidden=forbidden_content,
                    temp=self.temp,
                    strict=self.strict,
                    prompt_template=self.prompt_template,
                    glossary_dict=glossary_dict,
                    project_name=self.project_name,
                )
                processed_entries.append(segment_to_jsonl_entry(seg, entry.order))
            return processed_entries

        for entry in run_ordered_jsonl_pipeline(
            segments=self.segments,
            chunk_size=self.chunk_size,
            process_chunk=process_chunk,
            output_path=self.output_path,
        ):
            if not self._is_running:
                break
            self.progress_signal.emit(entry.order + 1)

        self.finished_signal.emit(self.segments)
