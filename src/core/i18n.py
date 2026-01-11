import sys
import json
from pathlib import Path

class I18nManager:
    def __init__(self, language="EN"):
        self.language = language
        self.translations = {}
        self.load_translations()

    def load_translations(self):
        if getattr(sys, 'frozen', False):
            # Running as bundled EXE
            base = Path(getattr(sys, '_MEIPASS'))
        else:
            # Running in dev mode
            base = Path(__file__).parent.parent.parent
            
        path = base / "resources" / "locales.json"
        
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    self.translations = json.load(f)
            except Exception as e:
                print(f"I18N Load Error: {e}")

    def set_language(self, lang_code: str):
        """Update the active UI language."""
        self.language = lang_code.upper()

    def t(self, key: str) -> str:
        """Translate a key based on current language."""
        # Get data for current lang, fallback to English if not found
        lang_data = self.translations.get(self.language, self.translations.get("EN", {}))
        return lang_data.get(key, key)

# Create global instance
I18N = I18nManager("EN")