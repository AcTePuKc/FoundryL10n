import ast
from pathlib import Path

import pytest

pytest.importorskip("typer")
pytest.importorskip("rich")


def _load_module_ast() -> ast.Module:
    source = Path("src/services/consistency_check.py").read_text(encoding="utf-8")
    return ast.parse(source)


def test_consistency_report_avoids_tm_models() -> None:
    tree = _load_module_ast()
    tm_names = {"TranslationMemoryIndex", "TranslationAuditRecord"}
    used_tm = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name) and node.id in tm_names}
    assert not used_tm, f"Unexpected TM model usage: {sorted(used_tm)}"


def test_consistency_report_uses_translation_record_fields() -> None:
    tree = _load_module_ast()
    allowed_attrs = {
        "__table__",
        "ai_draft",
        "id",
        "project_name",
        "segment_key",
        "source_text",
        "target_lang",
        "translation",
    }
    used_attrs = {
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "TranslationRecord"
    }
    assert "segment_key" in used_attrs
    assert used_attrs.issubset(allowed_attrs)
