import csv
from pathlib import Path

class ResourceLoader:
    @staticmethod
    def load_glossary(file_path: str) -> str:
        """Returns a string for the AI prompt."""
        path = Path(file_path)
        if not path.exists(): 
            return ""
        entries = []
        try:
            with open(path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f, delimiter='\t')
                for row in reader:
                    en = row.get('term', row.get('source', ''))
                    bg = row.get('translation', row.get('target', ''))
                    if en and bg:
                        entries.append(f"{en.strip()} -> {bg.strip()}")
            return "\n".join(entries)
        except: 
            return ""

    @staticmethod
    def load_glossary_dict(file_path: str) -> dict:
        """Returns a dictionary for the Python Audit Engine."""
        path = Path(file_path)
        if not path.exists(): 
            return {}
        glossary = {}
        try:
            with open(path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f, delimiter='\t')
                for row in reader:
                    en = row.get('term', row.get('source', ''))
                    bg = row.get('translation', row.get('target', ''))
                    if en and bg:
                        glossary[en.strip().lower()] = bg.strip().lower()
        except: 
            pass
        return glossary

    @staticmethod
    def load_style_guide(file_path: str) -> str:
        path = Path(file_path)
        return path.read_text(encoding='utf-8') if path.exists() else ""

    @staticmethod
    def load_forbidden_words(file_path: str) -> str:
        path = Path(file_path)
        if not path.exists(): 
            return ""
        return ", ".join([l.strip() for l in path.read_text(encoding='utf-8').splitlines() if l.strip()])