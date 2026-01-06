import csv
from pathlib import Path

class ResourceLoader:
    @staticmethod
    def load_glossary(file_path: str) -> str:
        path = Path(file_path)
        if not path.exists() or path.suffix not in ['.tsv', '.csv']:
            return ""
        
        entries = []
        try:
            with open(path, 'r', encoding='utf-8') as f:
                # Detect separator
                sep = '\t' if path.suffix == '.tsv' else ','
                reader = csv.DictReader(f, delimiter=sep)
                for row in reader:
                    # Look for term/translation columns
                    term = row.get('term', row.get('source', ''))
                    trans = row.get('translation', row.get('target', ''))
                    if term and trans:
                        entries.append(f"- {term} -> {trans}")
            return "\n".join(entries)
        except:
            return ""

    @staticmethod
    def load_style_guide(file_path: str) -> str:
        path = Path(file_path)
        if not path.exists():
            return "Follow standard localization practices."
        return path.read_text(encoding='utf-8')
    
    @staticmethod
    def load_forbidden_words(file_path: str) -> str:
        path = Path(file_path)
        if not path.exists():
            return ""
        try:
            # Read lines, strip whitespace, remove empty lines
            words = [line.strip() for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
            return ", ".join(words)
        except:
            return ""