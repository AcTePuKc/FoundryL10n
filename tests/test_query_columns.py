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
    test_engine = create_engine(f"sqlite:///{tmp_path / 'tm-columns.db'}")
    database.engine = test_engine
    database.init_db()
    try:
        yield database
    finally:
        database.engine = original_engine


def test_query_translation_memory_order_and_like(tm_db):
    tm_db.save_translation(
        source_text="Hello world",
        target_lang="FR",
        translation="Bonjour",
        project_name="demo",
        segment_key="seg-1",
        verified=True,
    )
    tm_db.save_translation(
        source_text="Hello there",
        target_lang="FR",
        translation="Salut",
        project_name="demo",
        segment_key="seg-2",
        verified=True,
    )

    results = tm_db.query_translation_memory("hello", "FR", "demo")

    assert [record.translation for record in results] == ["Salut", "Bonjour"]


def test_global_replace_in_db_targets_column(tm_db):
    tm_db.save_translation(
        source_text="Alpha Beta",
        target_lang="FR",
        translation="First Beta",
        project_name="demo",
        segment_key="seg-3",
        verified=False,
    )
    tm_db.save_translation(
        source_text="Hello World",
        target_lang="FR",
        translation="Bonjour",
        project_name="demo",
        segment_key="seg-4",
        verified=False,
    )

    replaced_translation = tm_db.global_replace_in_db(
        project_name="demo",
        target_lang="FR",
        find_text="Beta",
        replace_text="Gamma",
        search_source=False,
    )
    replaced_source = tm_db.global_replace_in_db(
        project_name="demo",
        target_lang="FR",
        find_text="World",
        replace_text="Universe",
        search_source=True,
    )

    assert replaced_translation == 1
    assert replaced_source == 1

    with Session(tm_db.engine) as session:
        statement = select(database.TranslationRecord).where(
            database.TranslationRecord.project_name == "demo",
            database.TranslationRecord.target_lang == "FR",
        )
        records = {record.source_text: record.translation for record in session.exec(statement).all()}

    assert records["Alpha Beta"] == "First Gamma"
    assert records["Hello Universe"] == "Bonjour"
