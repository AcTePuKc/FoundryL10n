# RLM Pipeline Design: Segmenter + Validator + Repair Loop

## Purpose

This document defines the design for the **RLM pipeline** (segmenter → validator → repair loop) and how it plugs into the existing FoundryL10n translation flow. It focuses on **placeholder/tag safety** in CAT workflows while preserving the current UI ergonomics (keyboard-driven editing, segment states, and minimal modal interruptions).

## Glossary

- **RLM:** Recursive Localization Model pipeline for tag-safe translation.
- **Segmenter:** Splits a line into typed segments (text vs. tag/placeholder).
- **Validator:** Compares source/target placeholder sequences for safety.
- **Repair loop:** A constrained LLM pass to fix placeholder placement without rephrasing.
- **CAT workflow:** Translator edits with source/target panes, QA markers, and segment states.

## Integration Overview (Existing Pipeline)

**Current flow (simplified):**

1. Source line read from dataset.
2. `masker` and tag utilities identify/normalize placeholders.
3. LLM translation via `LLMService` (single line or batch).
4. QA checks + UI indicators for tag safety and segment state.
5. Translator edits/accepts; QA marks errors and counters.

**RLM pipeline insertion (conceptual):**

- **Before LLM call:** Segmenter runs on the raw line (or masked line, depending on provider). Only text segments are sent to the LLM.
- **After LLM call:** Validator compares placeholder/tag sequence between source and candidate target. If invalid, Phase B adds a repair pass.
- **UI/QA:** Validation results are surfaced in the same QA markers and progress counters used today (blocking in strict mode; warning in non-strict).

## Segmenter API (Phase A)

### Inputs

- **raw_line (str):** Original source line as stored/imported.
- **masked_line (str | None):** Optional line after `masker` pass. Used when a provider's configuration specifies that masking rules should be applied before segmentation.
- **context (dict):** Optional context for segmentation decisions.
  - Example keys: `source_lang`, `target_lang`, `provider_id`, `is_strict`, `segment_id`.
- **metadata (dict):** Optional segment metadata.
  - Example keys: `tag_rules`, `override_patterns`, `allow_translatable_tags`.

### Outputs

- **segments (list[Segment]):**
  - `Segment(kind="text", value="...")`
  - `Segment(kind="tag", value="<TSMARKER_0>")`
  - `Segment(kind="tag", value="[BTN_OK]")`
  - `Segment(kind="tag", value="%s")`
  - `Segment(kind="tag", value="{0}")`
- **tags (list[str]):** Ordered list of tag/placeholder values extracted from the source.
- **risk_flags (list[str]):** Potential safety indicators for QA/UI.
  - Examples: `"nested_tag"`, `"unknown_bracketed"`, `"provider_override"`, `"unbalanced_delimiters"`.

### Error & Edge-Case Handling

- **Unbalanced delimiters:** If `<...` or `[...]` is not well-formed, emit a `risk_flags` entry and treat the entire token as `text` to avoid accidental tag stripping.
- **Unknown bracketed tokens:** Default to `tag` (conservative) unless provider overrides explicitly mark them translatable.
- **Mixed content within tag shells:** If a provider uses `<b>text</b>` and marks it as partially translatable, split into `tag`/`text`/`tag` segments per override rules.
- **Fallbacks:** If segmentation fails, return a single `Segment(kind="text", value=raw_line)` and set `risk_flags=["segmenter_fallback"]`.

## Validator API (Phase A)

### Inputs

- **source_segments (list[Segment])**
- **target_segments (list[Segment])** (derived from candidate translation)
- **source_tags (list[str])**
- **target_tags (list[str])**
- **context (dict)**
  - Example keys: `strict_mode`, `segment_id`, `provider_id`.

### Outputs

- **is_valid (bool)**: `true` when placeholder sequences match in order and multiplicity.
- **mismatches (list[dict])**: Details for QA and UI.
  - Example: `{"index": 2, "expected": "<TSMARKER_2>", "actual": "<TSMARKER_3>"}`
- **risk_flags (list[str])**: e.g. `"missing_tag"`, `"extra_tag"`, `"reordered_tags"`.

### Edge Cases

- **Duplicate tags:** Compare by order and multiplicity, not just set equality.
- **Provider overrides:** If a provider marks a token as translatable, it is excluded from the strict tag list.
- **Masked lines:** If masking replaced tags, validator must map through the same `masker` metadata for accurate comparison.

## Phase A: Segmenter + Validator (No Repair Loop)

**Goal:** Prevent tag corruption while keeping translator flow intact.

- Segment raw (or masked) source line.
- Translate **only text segments** through `LLMService`.
- Reassemble output by interleaving translated text with original tag segments.
- Validate placeholders between source and candidate target.
- UI/QA behavior:
  - **Strict mode:** block auto-accept and mark segment with a placeholder error badge.
  - **Non-strict:** allow but show a warning marker; do not interrupt typing/navigation.

## Phase B: Repair Pass + QA Integration

**Goal:** Automatically repair placeholder placement issues without rewriting translation.

### Repair Loop Inputs

- **source_line** + **candidate_translation**
- **source_tags** + **target_tags**
- **QA signals** (from validator + QA pipeline): missing tags, extra tags, reorder.
- **TM hints** (optional): if a prior verified translation exists, prefer its placeholder ordering.

### Repair Loop Behavior

- Call `LLMService` with a constrained prompt:
  - Instruct: *Fix tag/placeholder placement only; do not rewrite words.*
  - Provide explicit list of required placeholders in order.
- Re-run the validator after repair.
- If still invalid:
  - **Strict mode:** mark as blocking error; do not auto-accept.
  - **Non-strict:** accept best effort with a warning marker.

### QA Integration

- Expose repair attempts and outcomes in existing QA counters:
  - `repair_attempted`, `repair_success`, `repair_failed`.
- UI should show a lightweight indicator (icon/badge), not a modal dialog.
- Preserve segment state semantics (`draft`, `translated`, `verified`) and never auto-promote to `verified` when repairs were needed.

## Interaction with Existing Components

- **`masker`:**
  - Segmenter can run on `masked_line` when masking is already applied.
  - For strict matching, validator should compare **actual placeholder values** via masker metadata.
- **Tag utilities:**
  - Reuse existing placeholder detection rules for `%s`, `{0}`, `<TSMARKER_n>`, `[BTN_*]`.
  - Segmenter should be the central source of truth for tag extraction.
- **`LLMService`:**
  - Phase A: called on concatenated text segments only.
  - Phase B: called with repair prompt and placeholder list; no re-translation.
- **Batch translation flow:**
  - Segmenter/validator must be shared by both single-line and batch workers.
  - Repair loop should be opt-in for batch (e.g. enabled in strict mode or config).

## Risks & Guardrails (CAT Workflow)

- **Placeholder/tag corruption**
  - Guardrail: segmenter + validator must enforce order and multiplicity.
  - Risk: provider-specific tags might be misclassified (mitigate with overrides).
- **Partial/failed segments**
  - Guardrail: if LLM fails, preserve tags and surface a QA error without blocking editor focus.
  - Risk: batch flows could spam warnings; keep summary counters and avoid modal errors.
- **Human post-editing roundtrips**
  - Guardrail: always preserve placeholders in source/target panes; never auto-accept after repair.
  - Risk: repair could overwrite translator edits; only trigger on machine outputs, not on confirmed human edits.

## Open Questions / Assumptions

- Assumption: existing tag utilities already normalize placeholders and `masker` has a reversible mapping.
- Need to confirm: where QA counters are stored and surfaced (for repair metrics).
- Need to confirm: the exact strict/non-strict mode toggle API and its UI mapping.
