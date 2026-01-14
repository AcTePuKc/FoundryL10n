# Todo

This file is a working todo list for FoundryL10n.

> Note for tools/agents (Codex, etc.):
>
> * Only append new items; do not delete or rewrite existing ones.
> * Use GitHub checkbox syntax: `- [ ] Task description`.
> * Prefer small, concrete tasks over vague items.
>
>

---

## 1. Integration & Provider System

Tasks related to the modular plugin system and connecting to external platforms.

* [x] **Plugin Architecture:** Define the `Provider` base class and interface.
* [x] **Plugin Loader:** Implement logic to scan the `/plugins` directory for JSON/JS files.
* [x] **GitHub Sync:** Create a service to fetch/update the latest provider configs from the central GitHub repo.
* [x] **Generic API Client:** Build a flexible HTTP handler that uses headers/endpoints defined in the active plugin.
* [x] **Generic POC Provider:** Create the first official plugin file (`generic_example.json`) following the new schema.
* [x] **Auth Storage:** Implement secure local storage for API tokens (keyring/secret storage).
* [x] **Sync Logic:** Implement "Fetch Segments" and "Push Suggestions" actions within the UI.

---

## 2. UI / UX

Tasks related to the desktop UI, layouts, and editor behavior.

* [x] **Provider Selector:** Add a dropdown to select which website/provider to connect to.
* [x] **Login Modal:** Create a dynamic login form that adapts to the provider's requirements (User/Pass vs API Key).
* [x] **Sync Status Icons:** Add visual indicators to segments (e.g., "Synced", "Draft", "Conflict").
* [x] **Manual TSV Tools:** Add "Import TSV" and "Export TSV" buttons for file-based workflows.
* [x] **Focus Mode:** Implement a distraction-free editing view.

---

## 3. Engine / LLM

Tasks related to translation orchestration and local model behavior.

* [x] **Ollama Integration:** Ensure stable connection to local LLM endpoints.
* [x] **Context Awareness:** Pass "Current Translation" from the server to the LLM as context for better drafts.
* [x] **Tag Protection:** Implement regex-based validation to ensure LLM doesn't break game tags (e.g., `{0}`, `\n`).
* [x] **Prompt Templates:** Allow users to customize the LLM prompt per project.

---

## 4. Database / Persistence

Tasks about the local database schema and storage.

* [x] **Schema Update:** Add `provider_id` and `remote_id` to the segments table.
* [x] **Translation Memory:** Index successfully "Verified" translations for local reuse.
* [x] **History Tracking:** Log changes per segment to allow local rollbacks.
* [x] **Translation Memory:** Fix TranslationMemoryIndex to remove segment_key usage and update TM queries accordingly.

---

## 5. QA / Tooling

Tasks about validation and developer scripts.

* [x] **Consistency Check:** Script to find the same source text translated differently across a project.
* [x] **Plugin Validator:** Create a CLI tool to validate that a new `.json` plugin matches the required schema.
* [x] **Mock Server:** Set up a simple local server to test API integration without hitting live websites.
* [x] **Docs:** Add the integration architecture diagram + legend covering sync behavior.
* [x] **Docs:** Record the canonical plugin schema location and document UI validation/disablement behavior for invalid plugins.
* [x] **Docs:** Document BaseProvider method contracts and mapping rules in `docs/INTEGRATION.md`.

* [x] **Docs:** Add project context state model doc covering provider selection and sync transitions.

* [x] **Docs:** Add security documentation for keyring storage, key naming, and keyring fallback behavior.
* [x] **Docs:** Add DB mapping documentation + migration note for `provider_id`/`remote_id` (local-only projects use NULLs).
* [x] **Docs:** Document UI integration plan for Fetch/Submit placement, manual sync behavior, and segment status indicators.
* [x] **Docs:** Add stepwise implementation plan to `docs/ROADMAP.md`.

* [x] **Docs:** Align plugin directory references with `src/plugins` and confirm schema path in `docs/INTEGRATION.md`.
* [x] **Docs:** Finalize stepwise implementation plan guardrails in `docs/ROADMAP.md`.
* [x] **Plugin Loader tests:** Add pytest coverage for plugin discovery and validation.

* [x] Update consistency check status filters to use direct is_verified field references and cover them in tests.
* [x] Fix global_replace_in_db column query regression for SQLModel compatibility.
* [x] Note: Do not check items related to TM/consistency fixes until Pylance reports zero diagnostics for the specified lines (consistency_check.py now clean). This stops false “fixed” confirmations based only on tests. **When done:** keep the TM regression TODO item unchecked until stubs 1–3 are confirmed.
* [x] Remove segment_key usage from TranslationMemoryIndex indexing/filtering and keep TM scoped to source/target/project only.
* [x] Fix TranslationMemoryIndex segment_key regression.
* [x] Fix TM regression in query column references for SQLModel compatibility.
* [x] Docs: Add audit notes link in `docs/INTEGRATION.md` pointing to `docs/investigation.md` for UI refactor context.
* [x] Pylance reports clean diagnostics for `src/core/database.py` `.like()`/`.desc()` usage.
* [x] Pylance reports clean diagnostics for `src/services/consistency_check.py` `.is_()` usage.
* [x] Docs: Add Mock Server Quickstart section to `docs/INTEGRATION.md`.
* [x] Note: Keep the TM regression follow-ups above until they are resolved; they remain related to the Pylance gating milestone.
* [x] Docs: Update Mock Server path in Quickstart documentation.

* [x] Note: Runtime package clean after mock server move (no mock server imports in src).
* [x] Docs: Note README provider integration overview + config-driven communication in docs backlog.
* [x] Docs: Add style guide for ORM/type-checking rules and link it from integration docs.
* [ ] Note: Added optional JSON import format documentation and parser support alongside TSV.
