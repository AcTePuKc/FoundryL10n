from sqlmodel import Field, Session, SQLModel, create_engine, select
from typing import Optional
import hashlib
import json


class TranslationRecord(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    project_name: str = Field(default="default", index=True)
    source_hash: str = Field(index=True)
    source_text: str
    target_lang: str
    translation: str
    ai_draft: str = Field(default="")
    is_verified: bool = Field(default=False)
    never_translate: bool = Field(default=False)
    history_json: str = Field(default="[]")


sqlite_file_name = "foundry_memory.db"
sqlite_url = f"sqlite:///{sqlite_file_name}"
engine = create_engine(sqlite_url)


def init_db():
    SQLModel.metadata.create_all(engine)


def global_replace_in_db(project_name: str, target_lang: str, find_text: str, replace_text: str, search_source=False):
    """
    Nuclear Fix: Replaces text in the DB.
    search_source=True: search English (source_text)
    search_source=False: search in (translation)
    """
    with Session(engine) as session:
        target_col = getattr(
            TranslationRecord,
            "source_text" if search_source else "translation",
        )

        statement = select(TranslationRecord).where(
            TranslationRecord.project_name == project_name,
            TranslationRecord.target_lang == target_lang,
            target_col.like(f"%{find_text}%"),  # type: ignore[attr-defined]
        )

        records = session.exec(statement).all()

        for r in records:
            if search_source:
                r.source_text = r.source_text.replace(find_text, replace_text)
            else:
                r.translation = r.translation.replace(find_text, replace_text)

            r.is_verified = True
            session.add(r)

        session.commit()
        return len(records)


def get_cached_record(source_text: str, target_lang: str, project_name: str) -> Optional[TranslationRecord]:
    """Strict Lookup: Must match Source AND Language AND Project."""
    with Session(engine) as session:
        statement = select(TranslationRecord).where(
            TranslationRecord.source_text == source_text,
            TranslationRecord.target_lang == target_lang,
            TranslationRecord.project_name == project_name
        )
        return session.exec(statement).first()


def get_project_integrity_report(project_name: str, target_lang: str) -> list[dict]:
    """
    Returns a list of source texts that have inconsistent translations.
    Format: [ { "source": "...", "variants": { "translation1": count, "translation2": count } }, ... ]
    """
    with Session(engine) as session:
        statement = select(TranslationRecord).where(
            TranslationRecord.project_name == project_name,
            TranslationRecord.target_lang == target_lang,
        )
        records = session.exec(statement).all()

        master_map: dict[str, list[str]] = {}
        for r in records:
            src = r.source_text or ""
            trans = r.translation or ""
            if not src:
                continue
            master_map.setdefault(src, []).append(trans)

        report: list[dict] = []
        for src, trans_list in master_map.items():
            unique_trans = set(trans_list)
            if len(unique_trans) > 1:
                variants = {t: trans_list.count(t) for t in unique_trans}
                report.append({"source": src, "variants": variants})

        return report


def normalize_project_term(project_name: str, target_lang: str, source_text: str, correct_translation: str):
    """Force-updates all instances of a source text to a single translation."""
    with Session(engine) as session:
        statement = select(TranslationRecord).where(
            TranslationRecord.project_name == project_name,
            TranslationRecord.target_lang == target_lang,
            TranslationRecord.source_text == source_text
        )
        records = session.exec(statement).all()
        for r in records:
            r.translation = correct_translation
            r.is_verified = True  # Usually we verify them if we normalize them
            session.add(r)
        session.commit()


def find_translation_conflicts(project_name: str, target_lang: str) -> list[str]:
    """Finds English strings that have multiple different translations in the same project/lang."""
    with Session(engine) as session:
        statement = select(TranslationRecord).where(
            TranslationRecord.project_name == project_name,
            TranslationRecord.target_lang == target_lang,
        )
        records = session.exec(statement).all()

    source_map: dict[str, set[str]] = {}
    for r in records:
        if not r.translation:
            continue
        norm = r.translation.strip()
        if not norm:
            continue

        if r.source_text not in source_map:
            source_map[r.source_text] = set()
        source_map[r.source_text].add(norm)

    return [src for src, trans_set in source_map.items() if len(trans_set) > 1]


def save_translation(source_text: str, target_lang: str, translation: str, project_name="default",
                     verified=False, skip=False, ai_draft=""):
    source_hash = hashlib.md5(source_text.encode()).hexdigest()

    with Session(engine) as session:
        statement = select(TranslationRecord).where(
            TranslationRecord.source_text == source_text,
            TranslationRecord.target_lang == target_lang,
            TranslationRecord.project_name == project_name
        )
        existing = session.exec(statement).first()

        if existing:
            # HISTORY: move previous non-empty translation if it changed
            if existing.translation and existing.translation != translation:
                try:
                    history = json.loads(existing.history_json or "[]")
                except Exception:
                    history = []

                if existing.translation not in history:
                    history.append(existing.translation)
                    existing.history_json = json.dumps(history[-10:])

            existing.translation = translation
            existing.is_verified = verified
            existing.never_translate = skip

            if ai_draft and not existing.ai_draft:
                existing.ai_draft = ai_draft

            session.add(existing)
        else:
            record = TranslationRecord(
                source_hash=source_hash,
                source_text=source_text,
                target_lang=target_lang,
                translation=translation,
                is_verified=verified,
                never_translate=skip,
                ai_draft=ai_draft,
                project_name=project_name,
                history_json="[]",
            )
            session.add(record)

        session.commit()
