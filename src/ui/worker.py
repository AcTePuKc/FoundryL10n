from PySide6.QtCore import QThread, Signal
from core.engine import TranslationEngine
from services.resource_service import ResourceLoader


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
        engine = TranslationEngine(self.llm_service)
        loader = ResourceLoader()

        # 1. Load resources (String versions for LLM)
        glossary_text = loader.load_glossary(self.glossary_path)
        style_content = loader.load_style_guide(self.style_path)
        forbidden_content = loader.load_forbidden_words(self.forbidden_path)

        # 2. Load Dictionary version for the local Audit
        glossary_dict = loader.load_glossary_dict(self.glossary_path)

        for i, seg in enumerate(self.segments):
            if not self._is_running:
                break

            if seg.source_text and seg.source_text.strip():
                engine.run_translation(
                    [seg],
                    self.target_lang,
                    glossary=glossary_text,
                    style=style_content,
                    forbidden=forbidden_content,
                    temp=self.temp,
                    strict=self.strict,
                    prompt_template=self.prompt_template,
                    glossary_dict=glossary_dict,
                    project_name=self.project_name,
                )
            else:
                seg.translation = ""


            if not self._is_running:
                break
            self.progress_signal.emit(i + 1)

        self.finished_signal.emit(self.segments)
