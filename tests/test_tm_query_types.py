import pytest

sqlmodel = pytest.importorskip("sqlmodel")
from sqlmodel import create_engine

from core import database


@pytest.fixture()
def tm_db(tmp_path):
    original_engine = database.engine
    test_engine = create_engine(f"sqlite:///{tmp_path / 'tm-query-types.db'}")
    database.engine = test_engine
    database.init_db()
    try:
        yield database
    finally:
        database.engine = original_engine


def test_tm_query_filters_by_source_norm(tm_db):
    tm_db.save_translation(
        source_text="Hello there",
        target_lang="FR",
        translation="Salut",
        project_name="demo",
        segment_key="seg-1",
        verified=True,
    )
    tm_db.save_translation(
        source_text="Greetings friend",
        target_lang="FR",
        translation="Salutations",
        project_name="demo",
        segment_key="seg-2",
        verified=True,
    )

    results = tm_db.query_translation_memory("hello", "FR", "demo")

    assert [record.translation for record in results] == ["Salut"]


def test_tm_query_orders_by_desc_id(tm_db):
    tm_db.save_translation(
        source_text="Hello there",
        target_lang="FR",
        translation="Salut",
        project_name="demo",
        segment_key="seg-3",
        verified=True,
    )
    tm_db.save_translation(
        source_text="Hello world",
        target_lang="FR",
        translation="Bonjour",
        project_name="demo",
        segment_key="seg-4",
        verified=True,
    )

    results = tm_db.query_translation_memory("hello", "FR", "demo")

    assert [record.translation for record in results] == ["Bonjour", "Salut"]
