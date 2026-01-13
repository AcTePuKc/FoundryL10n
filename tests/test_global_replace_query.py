import pytest

sqlmodel = pytest.importorskip("sqlmodel")
from sqlmodel import Session, create_engine, select

try:
    from core import database
except Exception as exc:  # pragma: no cover - import guard
    pytest.skip(f"Database import failed: {exc}", allow_module_level=True)


@pytest.fixture()
def tm_db(tmp_path):
    original_engine = database.engine
    test_engine = create_engine(f"sqlite:///{tmp_path / 'tm-global-replace.db'}")
    database.engine = test_engine
    database.init_db()
    try:
        yield database
    finally:
        database.engine = original_engine


def test_global_replace_searches_target_column(tm_db):
    tm_db.save_translation(
        source_text="Source Alpha",
        target_lang="FR",
        translation="Alpha Target",
        project_name="demo",
        segment_key="seg-1",
        verified=False,
    )
    tm_db.save_translation(
        source_text="Beta Source",
        target_lang="FR",
        translation="Keep Target",
        project_name="demo",
        segment_key="seg-2",
        verified=False,
    )

    replaced = tm_db.global_replace_in_db(
        project_name="demo",
        target_lang="FR",
        find_text="Alpha",
        replace_text="Gamma",
        search_source=False,
    )

    assert replaced == 1

    with Session(tm_db.engine) as session:
        statement = select(database.TranslationRecord).where(
            database.TranslationRecord.project_name == "demo",
            database.TranslationRecord.target_lang == "FR",
        )
        records = {record.source_text: record.translation for record in session.exec(statement).all()}

    assert records["Source Alpha"] == "Gamma Target"
    assert records["Beta Source"] == "Keep Target"


def test_global_replace_searches_source_column(tm_db):
    tm_db.save_translation(
        source_text="Hello World",
        target_lang="FR",
        translation="Bonjour",
        project_name="demo",
        segment_key="seg-3",
        verified=False,
    )
    tm_db.save_translation(
        source_text="Hello Moon",
        target_lang="FR",
        translation="Salut",
        project_name="demo",
        segment_key="seg-4",
        verified=False,
    )

    replaced = tm_db.global_replace_in_db(
        project_name="demo",
        target_lang="FR",
        find_text="World",
        replace_text="Universe",
        search_source=True,
    )

    assert replaced == 1

    with Session(tm_db.engine) as session:
        statement = select(database.TranslationRecord).where(
            database.TranslationRecord.project_name == "demo",
            database.TranslationRecord.target_lang == "FR",
        )
        records = {record.source_text: record.translation for record in session.exec(statement).all()}

    assert "Hello Universe" in records
    assert records["Hello Universe"] == "Bonjour"
    assert records["Hello Moon"] == "Salut"
