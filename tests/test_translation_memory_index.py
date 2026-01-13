import pytest

sqlmodel = pytest.importorskip("sqlmodel")
from sqlmodel import create_engine

try:
    from core import database
except Exception as exc:  # pragma: no cover - import guard
    pytest.skip(f"Database import failed: {exc}", allow_module_level=True)


@pytest.fixture()
def tm_db(tmp_path):
    original_engine = database.engine
    test_engine = create_engine(f"sqlite:///{tmp_path / 'tm-index.db'}")
    database.engine = test_engine
    database.init_db()
    try:
        yield database
    finally:
        database.engine = original_engine


def test_tm_index_ignores_segment_key(tm_db):
    tm_db.save_translation(
        source_text="Hello",
        target_lang="FR",
        translation="Bonjour",
        project_name="demo",
        segment_key="seg-1",
        verified=True,
    )
    tm_db.save_translation(
        source_text="Hello",
        target_lang="FR",
        translation="Salut",
        project_name="demo",
        segment_key="seg-2",
        verified=True,
    )
    results = tm_db.query_translation_memory("hello", "FR", "demo")
    assert len(results) == 1
    assert results[0].translation == "Salut"


def test_tm_index_removed_when_unverified(tm_db):
    tm_db.save_translation(
        source_text="Goodbye",
        target_lang="FR",
        translation="Au revoir",
        project_name="demo",
        segment_key="seg-3",
        verified=True,
    )
    tm_db.save_translation(
        source_text="Goodbye",
        target_lang="FR",
        translation="Au revoir",
        project_name="demo",
        segment_key="seg-4",
        verified=False,
    )
    results = tm_db.query_translation_memory("goodbye", "FR", "demo")
    assert results == []
