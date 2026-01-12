import sys
import json
from pathlib import Path

FALLBACK_TRANSLATIONS = {
    "EN": {
        "i18n_load_error": "I18N Load Error: {error}",
    },
    "BG": {
        "i18n_load_error": "Грешка при зареждане на I18N: {error}",
    },
}


class I18nManager:
    def __init__(self, language="EN"):
        self.language = language
        self.translations = {}
        self.fallback_translations = FALLBACK_TRANSLATIONS
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
                error_template = self.fallback_translations.get(
                    self.language, self.fallback_translations.get("EN", {})
                ).get("i18n_load_error", "I18N Load Error: {error}")
                print(error_template.format(error=e))

    def set_language(self, lang_code: str):
        """Update the active UI language."""
        self.language = lang_code.upper()

    def t(self, key: str) -> str:
        """Translate a key based on current language."""
        # Get data for current lang, fallback to English if not found
        lang_data = self.translations.get(self.language, self.translations.get("EN", {}))
        if key in lang_data:
            return lang_data[key]
        fallback_lang_data = self.fallback_translations.get(
            self.language, self.fallback_translations.get("EN", {})
        )
        return fallback_lang_data.get(key, key)

# Create global instance
I18N = I18nManager("EN")
