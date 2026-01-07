from PySide6.QtCore import QThread, Signal
from core.engine import TranslationEngine
from services.resource_service import ResourceLoader

class TranslationWorker(QThread):
    progress_signal = Signal(int)
    finished_signal = Signal(list)

    def __init__(self, segments, target_lang, llm_service, glossary_path, style_path, forbidden_path, temp=0.1, prompt_template=""):
        super().__init__()
        self.segments = segments
        self.target_lang = target_lang
        self.llm_service = llm_service
        self.glossary_path = glossary_path
        self.style_path = style_path
        self.forbidden_path = forbidden_path
        self.temp = temp
        self._is_running = True
        self.prompt_template = prompt_template

    def stop(self):
        """Method to safely interrupt the loop."""
        self._is_running = False

    def run(self):
        engine = TranslationEngine(self.llm_service)
        loader = ResourceLoader()
        
        glossary_content = loader.load_glossary(self.glossary_path)
        style_content = loader.load_style_guide(self.style_path)
        forbidden_content = loader.load_forbidden_words(self.forbidden_path)

        for i, seg in enumerate(self.segments):
            # Check stop flag BEFORE starting a segment
            if not self._is_running:
                break
            
            # Only run the engine if there is actual text to process
            if seg.source_text and seg.source_text.strip():
                engine.run_translation(
                    [seg], 
                    self.target_lang, 
                    glossary=glossary_content, 
                    style=style_content, 
                    forbidden=forbidden_content,
                    temp=self.temp,
                    prompt_template=self.prompt_template
                )
            else:
                # If it's empty, we just mark it as empty and move on
                seg.translation = ""

            # Check stop flag AFTER the engine call
            if not self._is_running:
                break
                
            self.progress_signal.emit(i + 1)
        
        self.finished_signal.emit(self.segments)