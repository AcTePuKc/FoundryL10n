from sqlmodel import Field, Session, SQLModel, create_engine, select
from typing import Optional
from pathlib import Path

class TranslationRecord(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    source_hash: str = Field(index=True) # Hash of the original text
    source_text: str
    target_lang: str
    translation: str

# Create the database in the project root
sqlite_file_name = "foundry_memory.db"
sqlite_url = f"sqlite:///{sqlite_file_name}"
engine = create_engine(sqlite_url)

def init_db():
    SQLModel.metadata.create_all(engine)

def get_cached_translation(source_text: str, target_lang: str) -> Optional[str]:
    with Session(engine) as session:
        statement = select(TranslationRecord).where(
            TranslationRecord.source_text == source_text,
            TranslationRecord.target_lang == target_lang
        )
        results = session.exec(statement).first()
        return results.translation if results else None

def save_translation(source_text: str, target_lang: str, translation: str):
    import hashlib
    source_hash = hashlib.md5(source_text.encode()).hexdigest()
    
    with Session(engine) as session:
        # Check if it already exists to avoid duplicates
        existing = get_cached_translation(source_text, target_lang)
        if not existing:
            record = TranslationRecord(
                source_hash=source_hash,
                source_text=source_text,
                target_lang=target_lang,
                translation=translation
            )
            session.add(record)
            session.commit()