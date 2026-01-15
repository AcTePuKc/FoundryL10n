# FoundryL10n Roadmap

This document describes the high-level evolution of FoundryL10n as a modular CAT workstation.
Roadmap updates must not supersede or contradict already implemented features, and completed items should remain marked as done.

## 0.2 – Local CAT Refinement

**Focus:** Making the workstation reliable for individual offline use.

* [x] **Core Workflow:** Stabilize segment navigation and auto-save.
* [x] **Editor UX:** Implement Focus: Table/Editor modes and keyboard shortcuts ( to confirm).
* [x] **LLM Orchestration:** Improve local Ollama/LM Studio prompt templates for game-specific context.

## 0.3 – The Plugin Engine (Infrastructure)

**Focus:** Building the "Bridge" that allows external website integrations.

* [x] **Provider Interface:** Define the standard for how the app talks to external APIs.
* [x] **Plugin Loader:** Support loading `.json` or `.js` provider configs from a local `/plugins` folder.
* [x] **GitHub Sync:** Implement auto-updating of the `/plugins` folder from the central repository.
* [x] **Secure Vault:** Implement encrypted local storage for user API tokens and credentials.
* [x] **Implementation Plan:** Review and align stepwise commits with priorities, tests, and guardrails.

### Implementation Plan (stepwise commits)

1. **Step 1: Plugin loader skeleton**
   * **Affected modules:** `src/plugins/` (schema + fixtures), new loader in `src/services/` (e.g., `plugin_loader.py`), optional wiring in `src/main.py` for startup discovery.
   * **Guardrails:** Read-only discovery from `/plugins` (`.json`/`.js` only), no execution, no network access, ignore temp/hidden files, warn on duplicate IDs.
   * **Tests:** Unit coverage for discovery paths, deterministic ordering, and duplicate ID warnings.
   * **Quick verification:** Launch the app and confirm it logs or surfaces discovered plugin files from `/plugins` without validating.
2. **Step 2: Schema validation**
   * **Affected modules:** `src/plugins/schema.json`, validation utilities in `src/services/` (e.g., `plugin_validator.py`), error surfacing in `src/ui/main_window.py`.
   * **Acceptance criteria (guardrails):** Validation runs offline-first (no network calls), never triggers sync implicitly, and any submission-related fields are marked as suggestions-only (no publish semantics).
   * **Tests:** Validation cases for missing required fields, unsupported schema version, and malformed JSON.
   * **Quick verification:** Drop an invalid JSON in `/plugins` and confirm it appears disabled with a warning while valid plugins remain selectable.
3. **Step 3: BaseProvider interface**
   * **Affected modules:** new provider contract in `src/core/` (e.g., `providers/base.py`), integration wiring in `src/services/`.
   * **Acceptance criteria (guardrails):** Interface enforces explicit sync entry points only, forbids background sync, and exposes submit methods as suggestion-only (no direct publish).
   * **Tests:** Contract tests for stub provider implementations with no network side effects.
   * **Quick verification:** Instantiate a stub provider and confirm UI actions call the contract methods without network side effects.
4. **Step 4: UI hooks**
   * **Affected modules:** `src/ui/main_window.py`, `src/ui/editor_panel.py`, `src/ui/settings_tab.py` (provider selector, login, fetch/submit controls).
   * **UX guardrails:** Provider switching must preserve editor focus, segment navigation, and keyboard shortcuts.
   * **Acceptance criteria (guardrails):** Offline-first UX keeps editing fully functional without connectivity, sync is user-triggered via explicit controls only, and submit actions are labeled/treated as suggestions (not authoritative publishes).
   * **Quick verification:** Switch providers and confirm buttons enable/disable based on validation + auth state, without breaking segment navigation.
5. **Step 5: Keyring integration**
   * **Affected modules:** new credential helper in `src/services/` (e.g., `keyring_service.py`), auth flow updates in `src/ui/main_window.py`.
   * **Tests:** Mock keyring availability/unavailability to confirm persistence + fallback paths.
   * **Quick verification:** Store and retrieve a token across sessions when keyring is available; confirm in-memory fallback when not.

## 0.4 – First Integration: Generic POC Provider (Phase 1)

**Focus:** Proving the system works with a live community platform.

* [x] **Official Provider:** Release the `generic_example.json` POC plugin in `src/plugins/generic_example.json`.
* [x] **API Sync:** Implement Login -> Fetch Page -> Push Suggestion workflow.
* [x] **Conflict Management:** Visual UI for when a server string has changed compared to the local draft.
  * Already present: manual Fetch/Submit actions with remote sync indicators and last-sync tooltips.
  * Added: post-fetch remote change detection (compares fetched segments to local drafts/history) plus an inline, non-blocking diff panel in the editor with a tooltip marker.
* [x] **TSV Export:** Dedicated export profile for the initial generic POC provider workflows.

## 0.5 – QA & Translation Memory

**Focus:** Quality control and consistency across large projects.

* [x] **Tag Safety:** Automated validation to ensure LLMs don't corrupt game tags (e.g., `%s`, `{id}`).
* [x] **Local TM:** Searchable database of previous translations to suggest "matches" for new segments.
* [x] **Batch Processing:** Ability to "Submit All Verified" segments on a page in one click.

## 1.0 – Community Expansion

**Focus:** Scaling the ecosystem.

**Remaining unchecked items (next steps):** Advanced Mapping (see item below).

* [x] **Multi-Provider Support:** Open documentation for other communities to write their own plugins.
  * Note: Completed. The community-facing [PLUGIN_GUIDE.md](PLUGIN_GUIDE.md) is now available, complementing the existing [plugin system](../src/plugins/schema.json) and [integration docs](INTEGRATION.md).
* [x] **Advanced Mapping:** Allow plugins to define custom UI fields (e.g., "Character Gender" or "Max Length").
  * Note: Custom fields now support schema-defined metadata, UI rendering, persistence, and lightweight validation in the provider fields panel (`src/ui/editor_panel.py`) and submission flow (`src/ui/main_window.py`).
  * Minimal plan (**next steps**):
    1. **Schema extension + parsing (Phase A):** ✅ Completed. Provider-defined custom field metadata (labels, types, optionality, defaults, validation hints) now lives in the schema and is loaded alongside existing mapping paths.
    2. **Schema-to-UI adapter (Phase B):** ✅ Completed. Convert field metadata into editor widgets (reusing existing input types only) and render them inside the provider fields panel.
    3. **Data binding + persistence:** ✅ Completed. Store per-segment custom field values (e.g., `custom_fields` JSON keyed by field IDs) and include them in provider submission payloads when the provider mapping declares the field.
    4. **Validation + hints:** ✅ Completed. Surface provider constraints as non-blocking hints and lightweight warnings without interrupting typing flow.
  * Expected UX behavior:
    * Custom fields appear per-segment only when the active provider defines them; no fields show for providers without definitions.
    * If the panel is collapsed, show a subtle inline indicator (e.g., a small “fields” badge in the segment header row) only when custom fields exist for that segment to keep discoverability without adding extra global menu chrome.
    * Tabbing stays within the editor by default; users enter the custom field panel via a single explicit shortcut and return with Escape to preserve translation flow.
    * Field edits never steal focus from the target editor while typing unless the user explicitly focuses the panel.
  * Risks / guardrails:
    * **Keyboard flow regression:** Avoid adding fields to the default tab order; keep segment navigation shortcuts unchanged.
    * **Layout jitter:** Use fixed-height containers or collapse when empty to prevent editor resizing mid-typing.
    * **Validation friction:** Do not block segment confirmation on optional fields; only block on required fields at explicit submission time.
* [x] **Quality Dashboard:** UI for tracking progress, LLM usage stats, and accuracy.
  * Remaining gaps: progress/QA counters exist in the [main window UI](../src/ui/main_window.py), but there is no dedicated LLM usage or accuracy metrics breakdown yet.
  * Note: Metrics now surface batch duration, per-row average timing, and the active model name in the Metrics tab.
  * Next steps: instrument per-segment LLM usage (requests, tokens, latency), QA outcomes (tag errors, audit risks, verified rate), and surface a local-only summary in a dedicated Metrics tab.
* [x] **Placeholder-Safe Recursive Translation Pipeline:** Guarantee that non-translatable tokens survive LLM translation unchanged, with strict validation and repair.
  * Design reference: see [RLM_DESIGN.md](RLM_DESIGN.md) for Phase A (segmenter + validator, no auto-fix) and Phase B (repair pass + QA integration).
  * Scope:
    * Treat **any content wrapped in `<>` or `[]` as non-translatable by default**, unless a provider explicitly marks it as translatable.
    * Preserve existing placeholder patterns (`<TSMARKER_n>`, `<BR_n>`, `[BTN_*]`, `%s`, `{0}`, etc.) exactly, including order and multiplicity.
  * Apply the same rules in both GUI and CLI entry points via a shared core service layer.
  * Phase A (segmenter + validator): **completed**. See [RLM_DESIGN.md](RLM_DESIGN.md).
  * Phase B (repair pass + QA integration): **completed**.
  * Strict vs non-strict placeholder failure behavior: **implemented** (blocking error vs warning).

## Investigation status checklist (prevent duplicate roadmap work)

**Implemented**
* [x] **JSON/JSONL file import + export:** CLI/GUI support for JSON/JSONL parsing and export is in place.
* [x] **JSONL append-only persistence + resume-by-skip:** Append-only JSONL persistence now flushes per entry, skips translated keys on resume, and keeps deterministic mapping by `key`.
* [x] **Segment/tag validation + repair:** Placeholder/tag validation and repair passes are implemented in the shared translation engine.
* [x] **TSV/JSON array ⇄ JSONL converters:** Utility conversion script keeps stable key/index ordering and preserves note/empty translation fields.

**Pending**
* [ ] **(planned) CLI translation runner entry-point + reporting:** define required flags, defaults, per-chunk progress (segments completed/total), and per-file summary reporting for the CLI translation pipeline.
* [ ] **(planned) Strict LLM IO contract:** enforce schema-locked request/response formats, deterministic ordering, and hard placeholder parity checks for CLI/GUI parity.
* [x] **Placeholder failure handling policy:** retry-on-failure, skip + log unresolved segments, and manual review escalation rules when placeholders cannot be reconciled.
* [ ] **(planned) SQLModel `__table__` typing cleanup:** replace direct `__table__.c` access in TM query and consistency status filter with typed column access to satisfy static analysis.
* [ ] **(planned) UI non-blocking streaming translation integration:** worker threading + progress callbacks for streaming translation without blocking editor workflows.
