import pytest

sqlmodel = pytest.importorskip("sqlmodel")
from sqlmodel import create_engine

from core import database


@pytest.fixture()
def tm_db(tmp_path):
    original_engine = database.engine
    test_engine = create_engine(f"sqlite:///{tmp_path / 'tm.db'}")
    database.engine = test_engine
    database.init_db()
    try:
        yield database
    finally:
        database.engine = original_engine


def test_tm_index_updates_after_verify(tm_db):
    tm_db.save_translation(
        source_text="Hello",
        target_lang="FR",
        translation="Bonjour",
        project_name="demo",
        segment_key="seg-1",
        verified=False,
    )
    assert tm_db.query_translation_memory("Hello", "FR", "demo") == []

    tm_db.save_translation(
        source_text="Hello",
        target_lang="FR",
        translation="Bonjour",
        project_name="demo",
        segment_key="seg-1",
        verified=True,
    )
    results = tm_db.query_translation_memory("Hello", "FR", "demo")
    assert len(results) == 1
    assert results[0].translation == "Bonjour"


def test_tm_lookup_uses_normalized_source(tm_db):
    tm_db.save_translation(
        source_text="Hello   World",
        target_lang="FR",
        translation="Bonjour le monde",
        project_name="demo",
        segment_key="seg-2",
        verified=True,
    )
    results = tm_db.query_translation_memory("hello world", "FR", "demo")
    assert len(results) == 1
    assert results[0].translation == "Bonjour le monde"
