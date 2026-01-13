from sqlmodel import Field, Session, SQLModel, create_engine, select
from sqlalchemy import desc
from typing import Optional
from collections import Counter
import hashlib
import json


class TranslationRecord(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    project_name: str = Field(default="default", index=True)
    segment_key: str = Field(default="default", index=True)
    source_hash: str = Field(index=True)
    source_text: str
    target_lang: str
    translation: str
    ai_draft: str = Field(default="")
    is_verified: bool = Field(default=False)
    never_translate: bool = Field(default=False)
    history_json: str = Field(default="[]")


class TranslationAuditRecord(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    project_name: str = Field(index=True)
    source_text: str = Field(index=True)
    target_lang: str
    variants_json: str = Field(default="[]")


class TranslationMemoryIndex(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    project_name: str = Field(index=True)
    target_lang: str = Field(index=True)
    source_text: str
    source_norm: str = Field(index=True)
    translation: str


sqlite_file_name = "foundry_memory.db"
sqlite_url = f"sqlite:///{sqlite_file_name}"
engine = create_engine(sqlite_url)


def init_db():
    SQLModel.metadata.create_all(engine)


def _parse_history_list(history_json: str) -> list[str]:
    try:
        history = json.loads(history_json or "[]")
    except json.JSONDecodeError:
        return []
    if isinstance(history, list):
        return [h for h in history if isinstance(h, str)]
    return []


def _normalize_tm_text(text: str) -> str:
    return " ".join(text.lower().split())


def _store_audit_variants(
    session: Session,
    project_name: str,
    target_lang: str,
    source_text: str,
    variants: set[str],
) -> None:
    if not variants:
        return
    stmt = select(TranslationAuditRecord).where(
        TranslationAuditRecord.project_name == project_name,
        TranslationAuditRecord.target_lang == target_lang,
        TranslationAuditRecord.source_text == source_text,
    )
    existing = session.exec(stmt).first()
    if existing:
        prior = set(_parse_history_list(existing.variants_json))
        merged = sorted(prior | variants)
        existing.variants_json = json.dumps(merged)
        session.add(existing)
    else:
        record = TranslationAuditRecord(
            project_name=project_name,
            target_lang=target_lang,
            source_text=source_text,
            variants_json=json.dumps(sorted(variants)),
        )
        session.add(record)


def _upsert_tm_index(
    session: Session,
    project_name: str,
    target_lang: str,
    source_text: str,
    translation: str,
) -> None:
    source_norm = _normalize_tm_text(source_text)
    statement = select(TranslationMemoryIndex).where(
        TranslationMemoryIndex.project_name == project_name,
        TranslationMemoryIndex.target_lang == target_lang,
        TranslationMemoryIndex.source_norm == source_norm,
    )
    existing = session.exec(statement).first()
    if existing:
        existing.source_text = source_text
        existing.source_norm = source_norm
        existing.translation = translation
        session.add(existing)
    else:
        record = TranslationMemoryIndex(
            project_name=project_name,
            target_lang=target_lang,
            source_text=source_text,
            source_norm=source_norm,
            translation=translation,
        )
        session.add(record)


def _delete_tm_index(
    session: Session,
    project_name: str,
    target_lang: str,
    source_text: str,
) -> None:
    source_norm = _normalize_tm_text(source_text)
    statement = select(TranslationMemoryIndex).where(
        TranslationMemoryIndex.project_name == project_name,
        TranslationMemoryIndex.target_lang == target_lang,
        TranslationMemoryIndex.source_norm == source_norm,
    )
    existing = session.exec(statement).first()
    if existing:
        session.delete(existing)


def query_translation_memory(
    source_text: str,
    target_lang: str,
    project_name: str,
    limit: int = 10,
) -> list[TranslationMemoryIndex]:
    source_norm = _normalize_tm_text(source_text or "")
    if not source_norm:
        return []
    with Session(engine) as session:
        statement = (
            select(TranslationMemoryIndex)
            .where(
                TranslationMemoryIndex.project_name == project_name,
                TranslationMemoryIndex.target_lang == target_lang,
                TranslationMemoryIndex.source_norm.like(f"%{source_norm}%"),
            )
            .order_by(desc(TranslationMemoryIndex.id))
            .limit(limit)
        )
        return list(session.exec(statement).all())


def global_replace_in_db(
        project_name: str, 
        target_lang: str, 
        find_text: str, 
        replace_text: str, 
        search_source=False):
    """
    Nuclear Fix: Replaces text in the DB.
    search_source=True: search English (source_text)
    search_source=False: search in (translation)
    """
    with Session(engine) as session:
        target_col = (
            TranslationRecord.source_text
            if search_source
            else TranslationRecord.translation
        )

        statement = select(TranslationRecord).where(
            TranslationRecord.project_name == project_name,
            TranslationRecord.target_lang == target_lang,
            target_col.like(f"%{find_text}%"),
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


def get_cached_record(
        source_text: str,
        target_lang: str,
        project_name: str,
        segment_key: str | None = None) -> Optional[TranslationRecord]:
    """Strict Lookup: Must match source, language, project, and optional segment key."""
    with Session(engine) as session:
        statement = select(TranslationRecord).where(
            TranslationRecord.source_text == source_text,
            TranslationRecord.target_lang == target_lang,
            TranslationRecord.project_name == project_name,
        )
        if segment_key is not None:
            statement = statement.where(
                TranslationRecord.segment_key == segment_key
            )
        return session.exec(statement).first()


def get_project_integrity_report(project_name: str, target_lang: str):
    """Generates the data for the Integrity Hub, including history variants."""
    with Session(engine) as session:
        statement = select(TranslationRecord).where(
            TranslationRecord.project_name == project_name,
            TranslationRecord.target_lang == target_lang
        )
        records = session.exec(statement).all()

    master_map = {}  # normalized_src -> { "original_sources": set(), "variants": set() }

    for r in records:
        norm_src = " ".join(r.source_text.lower().split()).strip("!.?")

        if norm_src not in master_map:
            master_map[norm_src] = {"sources": set(), "variants": set()}

        master_map[norm_src]["sources"].add(r.source_text)

        # Add Active
        if r.translation and r.translation.strip():
            master_map[norm_src]["variants"].add(r.translation.strip())

        # Add History
        if r.history_json:
            try:
                h_list = json.loads(r.history_json)
                for h_trans in h_list:
                    if h_trans.strip():
                        master_map[norm_src]["variants"].add(h_trans.strip())
            except json.JSONDecodeError:
                pass

    report = []
    for norm_src, data in master_map.items():
        if len(data["variants"]) > 1:
            # We show all original English versions found (e.g. "Open" / "open")
            report.append({
                "source": " / ".join(data["sources"]),
                # Count simplified to 1 for UI
                "variants": {v: 1 for v in data["variants"]}
            })
    return report

def auto_normalize_all_conflicts(project_name: str, target_lang: str):
    """
    Finds all conflicts and automatically picks the most frequent 
    translation for each source text.
    """
    with Session(engine) as session:
        # 1. Get all records
        statement = select(TranslationRecord).where(
            TranslationRecord.project_name == project_name,
            TranslationRecord.target_lang == target_lang
        )
        records = session.exec(statement).all()
        
        # 2. Group by source -> {translation: count}
        source_map = {}
        for r in records:
            if r.source_text not in source_map:
                source_map[r.source_text] = []
            source_map[r.source_text].append(r.translation)
            
        updated_count = 0
        for src, trans_list in source_map.items():
            variants = Counter(trans_list)
            if len(variants) > 1:
                # This ensures if 'A' and 'B' both have 5 counts, 'A' is always picked.
                sorted_variants = sorted(variants.items(), key=lambda x: (-x[1], x[0]))
                best_translation = sorted_variants[0][0]
                
                # 3. Update all records for this source
                stmt = select(TranslationRecord).where(
                    TranslationRecord.project_name == project_name,
                    TranslationRecord.target_lang == target_lang,
                    TranslationRecord.source_text == src
                )
                to_update = session.exec(stmt).all()
                audit_variants: set[str] = set()
                for rec in to_update:
                    audit_variants.add(rec.translation)
                    audit_variants.update(_parse_history_list(rec.history_json))
                audit_variants.discard(best_translation)
                _store_audit_variants(
                    session,
                    project_name=project_name,
                    target_lang=target_lang,
                    source_text=src,
                    variants=audit_variants,
                )
                for rec in to_update:
                    if rec.translation != best_translation:
                        rec.translation = best_translation
                        updated_count += 1
                    rec.is_verified = True  # Mark as fixed
                    rec.history_json = json.dumps([best_translation])
                    session.add(rec)
        
        session.commit()
        return updated_count
    

def normalize_project_term(project_name: str, target_lang: str, source_text: str, correct_translation: str):
    """Force-updates all instances of a source text to a single translation."""
    with Session(engine) as session:
        statement = select(TranslationRecord).where(
            TranslationRecord.project_name == project_name,
            TranslationRecord.target_lang == target_lang,
            TranslationRecord.source_text == source_text
        )
        records = session.exec(statement).all()
        audit_variants: set[str] = set()
        for r in records:
            audit_variants.add(r.translation)
            audit_variants.update(_parse_history_list(r.history_json))
        audit_variants.discard(correct_translation)
        _store_audit_variants(
            session,
            project_name=project_name,
            target_lang=target_lang,
            source_text=source_text,
            variants=audit_variants,
        )
        for r in records:
            r.translation = correct_translation
            r.is_verified = True  # Usually we verify them if we normalize them
            r.history_json = json.dumps([correct_translation])
            session.add(r)
        session.commit()


def delete_record(source_text: str, target_lang: str, project_name: str):
    """Surgically removes a translation from the memory database."""
    with Session(engine) as session:
        statement = select(TranslationRecord).where(
            TranslationRecord.source_text == source_text,
            TranslationRecord.target_lang == target_lang,
            TranslationRecord.project_name == project_name
        )
        record = session.exec(statement).first()
        if record:
            session.delete(record)
            session.commit()
            return True
    return False


def find_translation_conflicts(project_name: str, target_lang: str) -> list[str]:
    """Finds English strings that have inconsistent translations (checking active + history)."""

    with Session(engine) as session:
        statement = select(TranslationRecord).where(
            TranslationRecord.project_name == project_name,
            TranslationRecord.target_lang == target_lang,
        )
        records = session.exec(statement).all()

    source_map: dict[str, set[str]] = {}

    for r in records:
        if not r.source_text:
            continue

        # We normalize the source slightly (ignore case/extra spaces) to find "hidden" conflicts
        # Example: "Spider-Man" and "spider-man" should be grouped together
        norm_source = " ".join(r.source_text.lower().split())

        if norm_source not in source_map:
            source_map[norm_source] = set()

        # 1. Add current active translation
        if r.translation and r.translation.strip():
            source_map[norm_source].add(r.translation.strip())

        # 2. Add History (Finding 1 fix: Look where the variants are hiding!)
        if not r.is_verified and r.history_json:
            for h_trans in _parse_history_list(r.history_json):
                if h_trans.strip():
                    source_map[norm_source].add(h_trans.strip())

    # 3. Clean Return: Only return sources that have more than 1 unique translation variant
    return [src for src, trans_set in source_map.items() if len(trans_set) > 1]


def save_translation(
    source_text: str,
    target_lang: str,
    translation: str,
    project_name: str = "default",
    segment_key: str = "default",  
    verified: bool = False,
    skip: bool = False,
    ai_draft: str = "",
):
    source_hash = hashlib.md5(source_text.encode()).hexdigest()

    with Session(engine) as session:
        statement = select(TranslationRecord).where(
            TranslationRecord.project_name == project_name,
            TranslationRecord.target_lang == target_lang,
            TranslationRecord.segment_key == segment_key,
            TranslationRecord.source_text == source_text,
        )
        existing = session.exec(statement).first()

        if existing:
            # HISTORY:
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
                project_name=project_name,
                segment_key=segment_key,
                source_hash=source_hash,
                source_text=source_text,
                target_lang=target_lang,
                translation=translation,
                is_verified=verified,
                never_translate=skip,
                ai_draft=ai_draft,
                history_json="[]",
            )
            session.add(record)

        should_index = bool(verified and translation and translation.strip() and not skip)
        if should_index:
            _upsert_tm_index(
                session,
                project_name=project_name,
                target_lang=target_lang,
                source_text=source_text,
                translation=translation,
            )
        else:
            _delete_tm_index(
                session,
                project_name=project_name,
                target_lang=target_lang,
                source_text=source_text,
            )

        session.commit()
