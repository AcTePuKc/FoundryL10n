import csv
from typing import List, Dict, Optional, Sequence
from pathlib import Path

class TranslationSegment:
    def __init__(self, key: str, source_text: str, context: str = "", original_row: Optional[Dict] = None):
        self.key = key
        self.source_text = source_text
        self.context = context
        self.original_row: Dict = original_row if original_row is not None else {}
        self.translation = ""
        self.thought = ""

class FoundryParser:
    def __init__(self):
        # Initializing headers as a list to avoid 'None' errors
        self.headers: List[str] = []
        self.text_col: str = ""
        self.target_col: str = ""

    def parse_tsv(self, file_path: Path) -> List[TranslationSegment]:
        segments: List[TranslationSegment] = []
        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f, delimiter='\t')
            
            # Fixed Pylance: Handle potential None for fieldnames
            raw_headers = reader.fieldnames
            if not raw_headers:
                # Fallback if file is empty or malformed
                self.headers = ["key", "source", "translation"]
            else:
                # Fixed Pylance: Convert Sequence to a List so we can append
                self.headers = list(raw_headers)
            
            # Fixed Pylance: Safe detection of columns
            self.text_col = next((h for h in self.headers if h.lower() in ['source', 'text', 'original']), self.headers[1] if len(self.headers) > 1 else "source")
            self.target_col = next((h for h in self.headers if h.lower() in ['translation', 'target', 'result']), "")
            
            if not self.target_col:
                self.target_col = 'translation'
                self.headers.append('translation')

            for row in reader:
                segments.append(
                    TranslationSegment(
                        key=row.get('key', ''),
                        source_text=row.get(self.text_col, ""),
                        context=row.get('note', row.get('context', '')),
                        original_row=row
                    )
                )
        return segments

    def save_tsv(self, segments: List[TranslationSegment], output_path: Path):
        if not segments: 
            return
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # If we lost headers during manual edit, reconstruct them purely from the row keys
        if not self.headers:
            self.headers = list(segments[0].original_row.keys())

        with open(output_path, 'w', encoding='utf-8', newline='') as f:
            # We explicitly use quoting=csv.QUOTE_NONE to ensure no extra quotes appear
            writer = csv.DictWriter(f, fieldnames=self.headers, delimiter='\t', extrasaction='ignore', quoting=csv.QUOTE_NONE)
            writer.writeheader()
            for seg in segments:
                row = seg.original_row.copy()
                # Clean up any leading/trailing whitespace in the keys to prevent "ghost" columns
                clean_row = {str(k).strip(): v for k, v in row.items()}
                clean_row[self.target_col] = seg.translation
                writer.writerow(clean_row)