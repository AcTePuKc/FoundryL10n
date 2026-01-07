from sqlmodel import Field, Session, SQLModel, create_engine, select
from typing import Optional
import hashlib

class TranslationRecord(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    source_hash: str = Field(index=True)
    source_text: str
    target_lang: str
    translation: str
    is_verified: bool = Field(default=False)
    never_translate: bool = Field(default=False)

sqlite_file_name = "foundry_memory.db"
sqlite_url = f"sqlite:///{sqlite_file_name}"
engine = create_engine(sqlite_url)

def init_db():
    SQLModel.metadata.create_all(engine)

def get_cached_record(source_text: str, target_lang: str) -> Optional[TranslationRecord]:
    with Session(engine) as session:
        statement = select(TranslationRecord).where(
            TranslationRecord.source_text == source_text,
            TranslationRecord.target_lang == target_lang
        )
        return session.exec(statement).first()

def save_translation(source_text: str, target_lang: str, translation: str, verified=False, skip=False):
    source_hash = hashlib.md5(source_text.encode()).hexdigest()
    with Session(engine) as session:
        statement = select(TranslationRecord).where(
            TranslationRecord.source_text == source_text,
            TranslationRecord.target_lang == target_lang
        )
        existing = session.exec(statement).first()
        
        if existing:
            existing.translation = translation
            existing.is_verified = verified 
            existing.never_translate = skip 
            session.add(existing)
        else:
            record = TranslationRecord(
                source_hash=source_hash, source_text=source_text,
                target_lang=target_lang, translation=translation,
                is_verified=verified, never_translate=skip
            )
            session.add(record)
        session.commit()