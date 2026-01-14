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

---

# Audit Note — GUI vs CLI translation path (prompt, tags, cleanup)

## Scope
Focused on the LLM translation pipeline for:
- Prompt template sourcing/usage.
- Tag masking/unmasking.
- Post-LLM cleanup steps.

## Findings
- **Prompt templates:** GUI reads/writes per-project templates via `QSettings` and passes them into `TranslationWorker`, which forwards the prompt to `TranslationEngine` and `LLMService`. CLI uses `_load_prompt_template()` in `main.py` and passes the same template into `TranslationEngine`. Both paths converge on `LLMService.translate_segment()` for prompt assembly and fallback behavior.【F:src/ui/settings_tab.py†L646-L678】【F:src/ui/worker.py†L41-L77】【F:src/main.py†L53-L190】【F:src/services/llm_service.py†L75-L132】
- **Tag masking:** Both GUI and CLI use `TranslationEngine.translate_single_segment()`, which masks tags with `Masker`, validates placeholders, and unmasks the response before applying tag error marking (strict mode). This is identical for both paths.【F:src/core/engine.py†L231-L299】【F:src/core/masker.py†L6-L33】
- **Cleanup:** LLM response cleanup (label stripping, polite junk removal, CJK safeguards) happens inside `LLMService.translate_segment()` and is shared by both GUI and CLI pipelines.【F:src/services/llm_service.py†L115-L177】

## Mismatch identified + fix
- **Mismatch:** GUI’s `TranslationWorker` was always invoked with default `strict=True`, ignoring the `strict_mode` setting from the Settings tab. This affects tag error cleanup (`[TAG ERROR]`) and strict tag preservation expectations in the GUI path compared to the intended strict toggle behavior. CLI already uses the engine default strictness and has no override, so the GUI should respect its UI setting for parity within the desktop pipeline.【F:src/ui/main_window.py†L1088-L1152】【F:src/ui/main_window.py†L2190-L2224】【F:src/ui/settings_tab.py†L910-L932】
- **Fix applied:** pass `strict=settings["strict_mode"]` when starting both single-row and bulk translation workers so the GUI pipeline honors the strict toggle consistently.【F:src/ui/main_window.py†L1105-L1145】【F:src/ui/main_window.py†L2199-L2224】
