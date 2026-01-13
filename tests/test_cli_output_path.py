import pytest

typer = pytest.importorskip("typer")
from typer.testing import CliRunner

import main


class DummyLLMService:
    def __init__(self, model_name: str):
        self.model = model_name


class DummyTranslationEngine:
    def __init__(self, llm_service):
        self.llm_service = llm_service

    def run_translation(self, segments, *args, **kwargs):
        for seg in segments:
            seg.translation = seg.translation or f"{seg.source_text}-translated"


def _write_sample_tsv(path):
    path.write_text("key\tsource\nline_1\tHello\n", encoding="utf-8")


def _setup_dummy_engine(monkeypatch):
    monkeypatch.setattr(main, "LLMService", DummyLLMService)
    monkeypatch.setattr(main, "TranslationEngine", DummyTranslationEngine)


def test_cli_default_output_path(tmp_path, monkeypatch):
    _setup_dummy_engine(monkeypatch)
    monkeypatch.chdir(tmp_path)

    input_path = tmp_path / "input.tsv"
    _write_sample_tsv(input_path)

    runner = CliRunner()
    result = runner.invoke(main.app, ["file", str(input_path), "--lang", "Spanish"])

    assert result.exit_code == 0
    assert (tmp_path / "out" / "Spanish" / "input.tsv").exists()


def test_cli_custom_output_path(tmp_path, monkeypatch):
    _setup_dummy_engine(monkeypatch)
    monkeypatch.chdir(tmp_path)

    input_path = tmp_path / "input.tsv"
    _write_sample_tsv(input_path)

    output_path = tmp_path / "exports" / "custom.tsv"
    runner = CliRunner()
    result = runner.invoke(
        main.app,
        ["file", str(input_path), "--lang", "Spanish", "--out", str(output_path)],
    )

    assert result.exit_code == 0
    assert output_path.exists()
    assert not (tmp_path / "out" / "Spanish" / "input.tsv").exists()
