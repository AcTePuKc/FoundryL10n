# Audit Note — Database TM/Replace + Consistency Status Filter

## Scope
Focused only on:
- `src/core/database.py` TM query and global replace usage of `__table__`.
- `src/services/consistency_check.py` status filter path using `__table__`.

## Pylance error locations (exact)
- `src/core/database.py:149` — `TranslationMemoryIndex.__table__.c` used to build TM query columns in `query_translation_memory`. Likely Pylance error: cannot access member `__table__` on `TranslationMemoryIndex` (SQLModel class) because the attribute is injected at runtime and not typed.【F:src/core/database.py†L139-L160】
- `src/core/database.py:175` — `TranslationRecord.__table__.c` used to pick columns in `global_replace_in_db`. Likely Pylance error: cannot access member `__table__` on `TranslationRecord` for the same reason.【F:src/core/database.py†L163-L200】
- `src/services/consistency_check.py:109` — `TranslationRecord.__table__.c` used to derive `target_col`/`is_verified_col`. Likely Pylance error: cannot access member `__table__` on `TranslationRecord`, causing the status filter lines to be flagged even though SQLAlchemy resolves them at runtime.【F:src/services/consistency_check.py†L109-L129】

## Current Pylance diagnostics (after stubs 1–2)
Running `python -m pyright src/core/database.py src/services/consistency_check.py` reports missing imports and SQLModel subclass typing issues:
- `src/core/database.py:1` — `Import "sqlmodel" could not be resolved` (reportMissingImports).
- `src/core/database.py:8` — incorrect keyword arguments for `__init_subclass__` (reportGeneralTypeIssues).
- `src/core/database.py:8` — no parameter named `table` (reportCallIssue).
- `src/core/database.py:22` — incorrect keyword arguments for `__init_subclass__` (reportGeneralTypeIssues).
- `src/core/database.py:22` — no parameter named `table` (reportCallIssue).
- `src/core/database.py:30` — incorrect keyword arguments for `__init_subclass__` (reportGeneralTypeIssues).
- `src/core/database.py:30` — no parameter named `table` (reportCallIssue).
- `src/services/consistency_check.py:9` — `Import "sqlalchemy.sql" could not be resolved` (reportMissingImports).
- `src/services/consistency_check.py:10` — `Import "sqlmodel" could not be resolved` (reportMissingImports).

## Suspected cause
`__table__` is dynamically attached by SQLModel/SQLAlchemy at runtime, but Pylance’s static typing for `SQLModel` does not advertise `__table__`, so any access like `TranslationRecord.__table__` or `TranslationMemoryIndex.__table__` is flagged even though it works at runtime. This shows up in TM short-listing and in the status filter condition because both rely on `__table__.c` columns for `.like()` and `.is_()` operations.【F:src/core/database.py†L139-L200】【F:src/services/consistency_check.py†L109-L129】

## Fix strategy (short)
- Prefer model column attributes directly (e.g., `TranslationMemoryIndex.source_norm`, `TranslationRecord.is_verified`) or `getattr(TranslationRecord, "translation")` to avoid `__table__` access.
- If table column access is truly needed, add a typed helper or local alias with explicit type casting to satisfy Pylance.
- Keep the query semantics unchanged (especially `like` filters and status filter values) while removing `__table__` usage to keep Pylance clean.
