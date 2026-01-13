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
    test_engine = create_engine(f"sqlite:///{tmp_path / 'tm-no-segment-key.db'}")
    database.engine = test_engine
    database.init_db()
    try:
        yield database
    finally:
        database.engine = original_engine


def test_tm_index_without_segment_key(tm_db):
    tm_db.save_translation(
        source_text="Hello",
        target_lang="FR",
        translation="Bonjour",
        project_name="demo",
        verified=True,
    )
    results = tm_db.query_translation_memory("hello", "FR", "demo")
    assert len(results) == 1
    assert results[0].translation == "Bonjour"


def test_tm_index_updates_across_segments(tm_db):
    tm_db.save_translation(
        source_text="Start",
        target_lang="FR",
        translation="Debut",
        project_name="demo",
        segment_key="seg-a",
        verified=True,
    )
    tm_db.save_translation(
        source_text="Start",
        target_lang="FR",
        translation="Commencer",
        project_name="demo",
        verified=True,
    )
    results = tm_db.query_translation_memory("start", "FR", "demo")
    assert len(results) == 1
    assert results[0].translation == "Commencer"
