# Audit Note — Database TM/Replace + Consistency Status Filter

*Last updated: 2026-01-15. This document is maintained incrementally as the investigation progresses.*

## Background
- Current batching operates on TSV/JSON line groups rather than per-segment streaming, so each batch waits for the full response before advancing.
- Observed latency: processing roughly 200 lines has taken ~20 minutes end-to-end in recent runs.
- Scaling concern: as file size grows, batch size and round-trip time grow proportionally, stretching translator wait time.
- Whole-file validation adds a fixed cost because validation/QA runs across the entire file after each batch.

## Findings / Stubs
This document ('docs/investigation.md') is the canonical location for future inspection findings.

## Roadmap prerequisites
- **Dependencies/Sequencing:** Roadmap items related to JSONL streaming, CLI runner, and strict IO contract need explicit ordering (e.g., schema definition → persistence/resume → CLI entry-point → UI non-blocking integration) plus dependencies on core/shared validation utilities to keep GUI/CLI parity.
- **Ownership:** Assign module-level owners (core/services/ui) or a single DRI for cross-cutting work (schema + persistence + UI), so follow-up tasks and review routing are clear.
- **Acceptance criteria:** Define success metrics (throughput targets, latency per chunk, placeholder parity pass rate) and verification steps (resume-by-skip replay, crash-safe append-only behavior) to prevent ambiguous “done” states.


New stubs should be appended as short subsections under this heading, following this convention:
- **Prefix** the subsection with the date and a brief title.
- **Include** links to any related files or issues for follow-up.

### 2026-01-15 — Placeholder validation + failure handling
- **Placeholder validation requirements:** enforce ordering and parity for tag/placeholder types, including:
  - `TSMARKER` sequence must remain ordered and complete across source/target (no reordering or loss).
  - `%s` tokens must match count and order.
  - `{0}`-style positional tokens must match count and order.
  - `[BTN_*]` tags must be preserved verbatim and in sequence.
- **Never commit on failure:** any placeholder validation failure blocks committing the segment.
- **Candidate failure handling:** on validation failure, attempt a retry; if still failing, skip and log the segment for later review; escalate to manual review when placeholders cannot be reconciled.

### 2026-01-16 — CLI entry-point, LLM contract, deliverables, open questions
- **CLI entry-point design (required flags + defaults + reporting expectations):**
  - Required flags: `--input`, `--output`, `--source-lang`, `--target-lang`, `--provider` (or `--provider-id`), with optional `--project-id`.
  - Defaults to document explicitly: `--chunk-size` (currently modeled as `20` in the conceptual API), `--strict` default `true`, `--progress` default `on` for terminal reporting.
  - Reporting expectations: emit per-chunk progress (segments completed / total), per-file summary (elapsed time, segments translated/skipped), and a machine-readable status code for automation.
- **Strict LLM IO contract:**
  - Enforce a deterministic, schema-locked request/response format with zero tolerance for schema drift.
  - Preserve placeholder integrity (counts, order, and identity) with hard failure on mismatch.
  - Maintain deterministic output ordering (input order is output order) for reproducibility and merge safety.
- **Concrete deliverables:**
  - Design doc covering CLI + JSONL schema, placeholder validation rules, and resume strategy.
  - Optional prototype (CLI translation runner + JSONL append-only writer).
  - Constraints checklist (LLM contract, placeholder integrity, no schema drift, deterministic ordering, resume safety).
- **Open questions:**
  - `chunk_size` default (confirm `20` or set a new baseline).
  - Expected speedup vs current batch flow (target latency/throughput).
  - Parallelism model (async tasks vs multi-process workers; ordering guarantees).
  - Large-file progress storage (append-only JSONL vs separate checkpoint file).
  - UI non-blocking integration (worker threading + progress callbacks without blocking segment editing).

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

---

# JSONL Streaming Translation Investigation — Roadmap + Integration Notes

## Goals
- **JSONL internal format:** define the canonical per-line object schema used by the streaming pipeline (required fields, optional metadata, and placeholder/tag representation) so translators and tools can reason about segment payloads consistently.
- **Mapping from TSV/JSON:** document how TSV rows and JSON segment objects normalize into the JSONL schema (field mapping, default values, and preservation of `key`, `source`, `translation`, and notes/context).
- **Round-trip expectations:** clarify what data must survive TSV/JSON → JSONL → TSV/JSON exports without loss, and what fields are best-effort or may be recomputed.
- **Segment definition options:** outline whether segments are defined per row, per sentence, or by a custom segmentation strategy, and how those choices affect keys, ordering, and QA.
- **`chunk_size` tradeoffs:** capture guidance on chunking by token count vs. segment count, expected latency/throughput impacts, and how chunk size affects placeholder/tag correctness.

## Roadmap touchpoints
- **Batch Processing (0.5 QA & Translation Memory):** roadmap calls out the ability to “Submit All Verified” segments on a page in one click, which frames batch-oriented workflows alongside streaming translation behavior.【F:docs/ROADMAP.md†L53-L59】

## Incremental JSONL persistence + resume strategy
- **Append-only vs update semantics:** JSONL persistence should be append-first for streaming batches. Each translated segment writes a new line with the canonical `key` plus translation payload. Updates are modeled as additional lines for the same `key` (latest wins on replay), not in-place mutation, to keep writes sequential and avoid partial-line corruption when a crash occurs mid-update.
- **Resume strategy (skip translated keys):** on restart, re-scan the JSONL output and build a `key → last translation` index. Incoming segments whose keys already have a non-empty translation should be skipped by default (treat as already translated). This makes resume idempotent and avoids reissuing LLM calls for completed segments.
- **Crash-safety guarantees:** append-only writes can be made crash-safe by fsyncing after each JSONL line (or after a small batch) and by treating any trailing partial line as incomplete and ignorable on resume. This ensures that a crash never corrupts prior lines, and the worst case is losing the last in-flight line.
- **Forward-looking worker model:** the initial implementation assumes a single-threaded, in-process worker that streams translations sequentially and appends JSONL lines in order. A future `--workers N` flag can switch to a multi-worker model (either in-process async tasks or multi-process workers). In both cases, JSONL persistence remains append-only, and ordering can be preserved via a coordinator that serializes writes or uses per-worker temp files merged deterministically.

## Integration requirements relevant to JSONL streaming
- **Optional JSON/JSONL Import:** JSON and JSONL can be imported alongside TSV. JSON accepts a list of objects (or `{ "segments": [...] }`); JSONL expects one object per line. Minimal fields are `key` and `source`; `translation`, `context`, `note`, `custom_fields`, `ai_draft`, `provider_id`, `remote_id`, and sync timestamps are optional.【F:docs/INTEGRATION.md†L399-L400】
- **Remote-synced context awareness:** when segments originate from a remote provider, the LLM context includes the remote source + target text, and drafting remains manual (no auto-sync).【F:docs/INTEGRATION.md†L399-L400】

## Integration with repo structure
- **`src/core/`:** streaming translation pipeline, segmentation/validation, and data normalization helpers (e.g., `core/translation_pipeline.py`, `core/segment_validator.py`, `core/jsonl_persistence.py`).
- **`src/services/`:** provider-facing integrations, LLM streaming client, remote sync adapters (e.g., `services/llm_client_streaming.py`, `services/provider_gateway.py`).
- **`src/ui/`:** UI-facing orchestration and worker wiring for batch/streaming translation (e.g., `ui/translation_worker.py`, `ui/streaming_controller.py`).
- **`tools/`:** one-off scripts and profiling helpers for pipeline experiments (e.g., `tools/streaming_bench.py`, `tools/jsonl_replay.py`).

Suggested module layout (non-binding, aligns with existing responsibilities):
- `core/translation_pipeline.py`: `translate_file(...)` orchestration, per-segment streaming, and JSONL persistence entry points.
- `core/segment_validator.py`: placeholder/tag validation utilities shared by CLI + UI.
- `services/llm_client_streaming.py`: streaming client abstraction for providers that support incremental tokens.

High-level UI-facing API (conceptual):
```python
# Required imports:
# from pathlib import Path
# from typing import Callable
# from some_module import CancelToken, TranslationRunResult
def translate_file(
    *,
    input_path: Path,
    output_path: Path,
    source_lang: str,
    target_lang: str,
    provider_id: str,
    project_id: str | None = None,
    chunk_size: int = 20,
    strict_mode: bool = True,
    progress_cb: Callable[[int, int], None] | None = None,
    cancel_token: CancelToken | None = None,
) -> TranslationRunResult: ...
```

Note: This summary is mirrored in README.md.
