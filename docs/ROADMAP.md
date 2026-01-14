# FoundryL10n Roadmap

This document describes the high-level evolution of FoundryL10n as a modular CAT workstation.

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

* [x] **Multi-Provider Support:** Open documentation for other communities to write their own plugins.
  * Note: Completed. The community-facing [PLUGIN_GUIDE.md](PLUGIN_GUIDE.md) is now available, complementing the existing [plugin system](../src/plugins/schema.json) and [integration docs](INTEGRATION.md).
* [ ] **Advanced Mapping:** Allow plugins to define custom UI fields (e.g., "Character Gender" or "Max Length").
  * Note: mapping paths exist in the [schema](../src/plugins/schema.json). The app now has a **collapsible provider fields panel shell** in the editor, but no field metadata wiring or persistence yet.
  * Minimal plan (**next steps**):
    1. **Schema-to-UI adapter:** Read provider-defined field metadata (label, type, optionality, default, validation hints) and map to existing editor widgets without adding new field types.
    2. **Field container placement:** ✅ **Shell in place.** Render custom fields in a compact, collapsible panel adjacent to the segment editor (not inline with the target editor) to avoid shifting the translation caret.
    3. **Data binding:** Persist values in per-segment metadata alongside imported TSV rows (e.g., an optional `custom_fields` JSON blob keyed by provider field IDs) so storage stays format-neutral and future DB storage can mirror the same structure; include values in provider submission payloads only when the provider declares a mapping key.
    4. **Validation and feedback:** Surface provider constraints as non-blocking hints and lightweight warnings (no modal interruptions while typing).
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
  * Next steps: instrument per-segment LLM usage (requests, tokens, latency), QA outcomes (tag errors, audit risks, verified rate), and surface a local-only summary in a dedicated Metrics tab.
* [ ] **Placeholder-Safe Recursive Translation Pipeline:** Guarantee that non-translatable tokens survive LLM translation unchanged, with strict validation and repair.
  * Design reference: see [RLM_DESIGN.md](RLM_DESIGN.md) for Phase A (segmenter + validator, no auto-fix) and Phase B (repair pass + QA integration).
  * Scope:
    * Treat **any content wrapped in `<>` or `[]` as non-translatable by default**, unless a provider explicitly marks it as translatable.
    * Preserve existing placeholder patterns (`<TSMARKER_n>`, `<BR_n>`, `[BTN_*]`, `%s`, `{0}`, etc.) exactly, including order and multiplicity.
    * Apply the same rules in both GUI and CLI entry points via a shared core service layer.
  * Minimal plan (no implementation yet; next steps):
    1. **Segmenter layer (parser):**
       * Introduce a small, provider-agnostic segmenter that splits a source string into a sequence of typed segments, e.g.:
         * `Segment(kind="tag", value="<TSMARKER_0>")`
         * `Segment(kind="tag", value="[BTN_OK]")`
         * `Segment(kind="text", value="plain text here")`
       * Tag detection rules:
         * Anything that matches `^<.*>$` (single-segment) or known placeholder patterns is `kind="tag"` and must not be translated.
         * Anything that matches `^\[.*\]$` (single-segment) is `kind="tag"` by default and must not be translated.
         * Everything else is `kind="text"`.
       * Keep the segmenter in a reusable module (e.g. `core/translation/segments.py`) so both GUI and background workers share the same logic.
    2. **LLM-facing translation wrapper:**
       * Replace the “translate whole string” call with a wrapper that:
         * Runs the segmenter.
         * Sends **only `kind="text"` segments** to the LLM for translation.
         * Re-assembles the final string by interleaving translated text segments with original tag segments *without modification*.
       * Ensure fuzzy suggestions, translation memory lookups, and provider calls work at the segment/text level without ever touching tag segments.
    3. **Placeholder validation + recursive repair:**
       * Implement a validator that compares the placeholder sequence between source and candidate translation:
         * Extract all tag segments and simple placeholders (`%s`, `{0}`, etc.) from both source and translation.
         * Validation succeeds only if the sequence (length, order, and exact values) matches.
       * On failure, run a **second-pass “repair” step**:
         * Provide the LLM with both source and broken translation and instruct it to **only fix tag/placeholder placement** without altering wording.
         * Re-validate after repair.
       * If repair still fails in strict mode:
         * Mark the segment as “placeholder error” and do not auto-accept; surface this state to the QA/progress system.
       * In non-strict mode:
         * Accept the best-effort repair but flag the segment with a non-blocking warning for the user.
    4. **Config and escape hatches:**
       * Add a provider-level configuration hook for **override rules**, e.g.:
         * Allow specific tag patterns like `<b>…</b>` or `[color=red]…[/color]` where the *inner text* is translatable but the tag shell is not.
         * Allow future providers to mark specific bracketed patterns as translatable or partially translatable.
       * Keep the default behavior conservative: “anything fully wrapped in `<>` or `[]` is non-translatable” unless configuration explicitly relaxes it.
    5. **Integration with strict/non-strict and QA:**
       * Wire placeholder validation results into the existing strict-mode toggle and QA counters:
         * Strict mode: a failed placeholder check (after repair attempts) counts as a blocking error for that segment.
         * Non-strict mode: show a subtle warning icon/badge instead of blocking, and let the user decide.
       * Ensure batch translation workers and single-line translation flows both use the same validation + repair pipeline so behavior is consistent everywhere.
  * Expected behavior:
    * LLM output can no longer “eat” or re-order `<TSMARKER_*>`, `[BTN_*]`, `%s`, `{0}`, etc.; these are treated as immutable structure.
    * Any content that arrives inside `<>` or `[]` is preserved as-is by default, unless the active provider explicitly overrides the rule.
    * Users see clear, minimal QA feedback when a line cannot be auto-repaired, without modal dialogs interrupting typing or navigation.
  * Risks / guardrails:
    * **Regression in fuzzy suggestions / TM:** Make sure fuzzy/TM suggestions are generated and displayed using the same segment model so tags stay untouched there as well.
    * **Overly aggressive protection:** Default “protect everything in `<>` / `[]`” is conservative; override rules must be easy to add for markup-heavy providers.
    * **Performance:** Segmenting + validating every line adds overhead; keep the parser simple and avoid complex nested parsing unless a provider truly needs it.
