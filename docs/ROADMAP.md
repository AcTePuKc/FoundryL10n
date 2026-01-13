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
* [ ] **GitHub Sync:** Implement auto-updating of the `/plugins` folder from the central repository.
  * Remaining gaps: sync service exists but there is no UI menu/toolbar action or CLI command to trigger a user-initiated plugin sync.
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
* [ ] **Conflict Management:** Visual UI for when a server string has changed compared to the local draft.
  * Remaining gaps: remote change detection and the visual diff UI are not implemented; current conflict tooling is focused on the local Translation Memory.
* [x] **TSV Export:** Dedicated export profile for the initial generic POC provider workflows.

## 0.5 – QA & Translation Memory

**Focus:** Quality control and consistency across large projects.

* [x] **Tag Safety:** Automated validation to ensure LLMs don't corrupt game tags (e.g., `%s`, `{id}`).
* [x] **Local TM:** Searchable database of previous translations to suggest "matches" for new segments.
* [ ] **Batch Processing:** Ability to "Submit All Verified" segments on a page in one click.
  * Remaining gaps: no UI/CLI action exists to submit all verified segments in bulk; only per-segment verified status and suggestion submission are available.

## 1.0 – Community Expansion

**Focus:** Scaling the ecosystem.

* [ ] **Multi-Provider Support:** Open documentation for other communities to write their own plugins.
  * Note: partially implemented via the plugin system + integration docs; community-facing guide still missing.
* [ ] **Advanced Mapping:** Allow plugins to define custom UI fields (e.g., "Character Gender" or "Max Length").
  * Note: partially implemented with mapping paths in the schema/client, but no custom UI field rendering yet.
* [ ] **Quality Dashboard:** UI for tracking progress, LLM usage stats, and accuracy.
  * Note: partially implemented with basic status counters in the bottom bar; no full dashboard yet.
