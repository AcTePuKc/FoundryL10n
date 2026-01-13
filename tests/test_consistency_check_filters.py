import ast
from pathlib import Path

import pytest

pytest.importorskip("typer")
pytest.importorskip("rich")


def _load_module_ast() -> ast.Module:
    source = Path("src/services/consistency_check.py").read_text(encoding="utf-8")
    return ast.parse(source)


def _has_is_verified_alias(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "is_verified_col"
            for target in node.targets
        ):
            if (
                isinstance(node.value, ast.Attribute)
                and isinstance(node.value.value, ast.Name)
                and node.value.value.id == "TranslationRecord"
                and node.value.attr == "is_verified"
            ):
                return True
    return False


def _has_is_verified_filter(tree: ast.AST, value: bool) -> bool:
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "is_"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "is_verified_col"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and node.args[0].value is value
        ):
            return True
    return False


def test_status_filters_use_is_verified_field() -> None:
    tree = _load_module_ast()

    assert _has_is_verified_alias(tree), "Expected is_verified_col alias for TranslationRecord.is_verified."
    assert _has_is_verified_filter(tree, True), "Expected verified filter to use is_verified_col.is_(True)."
    assert _has_is_verified_filter(tree, False), "Expected unverified filter to use is_verified_col.is_(False)."

    source = Path("src/services/consistency_check.py").read_text(encoding="utf-8")
    assert "TranslationRecord.__table__.c.is_verified" not in source
