import csv
import json
from typing import List, Dict, Optional
from pathlib import Path

class TranslationSegment:
    def __init__(
        self,
        key: str,
        source_text: str,
        context: str = "",
        translation: str = "",
        original_row: Optional[Dict] = None,
        ai_draft: str = "",
        provider_id: Optional[str] = None,
        remote_id: Optional[str] = None,
        last_sync: Optional[str] = None,
        remote_changed: bool = False,
    ):
        self.key = key
        self.source_text = source_text
        self.context = context
        self.original_row: Dict = original_row if original_row is not None else {}
        self.translation = translation
        self.thought = ""
        self.ai_draft = ai_draft
        self.provider_id = provider_id
        self.remote_id = remote_id
        self.last_sync = last_sync
        self.remote_changed = remote_changed
        self.has_conflict = False
        self.is_verified = False
        self.never_translate = False
        self.repair_attempted = False
        self.repair_success = False
        self.repair_failed = False

    @staticmethod
    def resolve_sync_timestamp(row: Dict) -> str | None:
        return (
            row.get("last_sync")
            or row.get("synced_at")
            or row.get("updated_at")
        )


class FoundryParser:
    def __init__(self):
        # Initializing headers as a list to avoid 'None' errors
        self.headers: List[str] = []
        self.text_col: str = ""
        self.target_col: str = ""
        self._custom_fields_col = "custom_fields"

    def _parse_custom_fields(self, value: object) -> Dict:
        if not value:
            return {}
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                return {}
            return parsed if isinstance(parsed, dict) else {}
        return {}

    def _serialize_custom_fields(self, value: object) -> str:
        if not value:
            return ""
        if isinstance(value, str):
            return value
        try:
            return json.dumps(value, ensure_ascii=False)
        except (TypeError, ValueError):
            return ""

    def parse_tsv(self, file_path: Path) -> List[TranslationSegment]:
        segments: List[TranslationSegment] = []
        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f, delimiter='\t')
            
            raw_headers = reader.fieldnames
            if not raw_headers:
                self.headers = ["key", "source", "translation"]
            else:
                self.headers = list(raw_headers)
            
            self.text_col = next((h for h in self.headers if h.lower() in ['source', 'text', 'original']), 
                                 self.headers[1] if len(self.headers) > 1 else "source")
            self.target_col = next((h for h in self.headers if h.lower() in ['translation', 'target', 'result']), "")
            
            if not self.target_col:
                self.target_col = 'translation'
                self.headers.append('translation')

            for row in reader:
                existing_trans = row.get(self.target_col, "")
                existing_draft = row.get('ai_draft', "")
                provider_id = row.get("provider_id") or None
                remote_id = row.get("remote_id") or None
                last_sync = (
                    row.get("last_sync")
                    or row.get("synced_at")
                    or row.get("updated_at")
                )
                if self._custom_fields_col in row:
                    row[self._custom_fields_col] = self._parse_custom_fields(
                        row.get(self._custom_fields_col)
                    )
                
                segments.append(
                    TranslationSegment(
                        key=row.get('key', 'no_key'),
                        source_text=row.get(self.text_col, ""),
                        context=row.get('note', row.get('context', '')),
                        translation=existing_trans,
                        ai_draft=existing_draft,
                        original_row=row,
                        provider_id=provider_id,
                        remote_id=remote_id,
                        last_sync=last_sync,
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
        if any(
            isinstance(getattr(seg, "original_row", {}), dict)
            and self._custom_fields_col in (seg.original_row or {})
            for seg in segments
        ) and self._custom_fields_col not in self.headers:
            self.headers.append(self._custom_fields_col)

        with open(output_path, 'w', encoding='utf-8', newline='') as f:
            # We use QUOTE_MINIMAL to quote only fields that need it (tabs/newlines/quotes).
            writer = csv.DictWriter(
                f,
                fieldnames=self.headers,
                delimiter='\t',
                extrasaction='ignore',
                quoting=csv.QUOTE_MINIMAL,
            )
            writer.writeheader()
            for seg in segments:
                row = seg.original_row.copy()
                # Clean up any leading/trailing whitespace in the keys to prevent "ghost" columns
                clean_row = {str(k).strip(): v for k, v in row.items()}
                clean_row[self.target_col] = seg.translation
                if self._custom_fields_col in clean_row:
                    clean_row[self._custom_fields_col] = self._serialize_custom_fields(
                        clean_row.get(self._custom_fields_col)
                    )
                writer.writerow(clean_row)
