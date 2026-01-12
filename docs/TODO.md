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

* [ ] **Plugin Architecture:** Define the `Provider` base class and interface.
* [x] **Plugin Loader:** Implement logic to scan the `/plugins` directory for JSON/JS files.
* [ ] **GitHub Sync:** Create a service to fetch/update the latest provider configs from the central GitHub repo.
* [ ] **Generic API Client:** Build a flexible HTTP handler that uses headers/endpoints defined in the active plugin.
* [ ] **AdventurersBG Provider:** Create the first official plugin file (`adventurers_bg.json`) following the new schema.
* [ ] **Auth Storage:** Implement secure local storage for API tokens (keyring/secret storage).
* [ ] **Sync Logic:** Implement "Fetch Segments" and "Push Suggestions" actions within the UI.

---

## 2. UI / UX

Tasks related to the desktop UI, layouts, and editor behavior.

* [ ] **Provider Selector:** Add a dropdown to select which website/provider to connect to.
* [ ] **Login Modal:** Create a dynamic login form that adapts to the provider's requirements (User/Pass vs API Key).
* [ ] **Sync Status Icons:** Add visual indicators to segments (e.g., "Synced", "Draft", "Conflict").
* [ ] **Manual TSV Tools:** Add "Import TSV" and "Export TSV" buttons for file-based workflows.
* [ ] **Focus Mode:** Implement a distraction-free editing view.

---

## 3. Engine / LLM

Tasks related to translation orchestration and local model behavior.

* [ ] **Ollama Integration:** Ensure stable connection to local LLM endpoints.
* [ ] **Context Awareness:** Pass "Current Translation" from the server to the LLM as context for better drafts.
* [ ] **Tag Protection:** Implement regex-based validation to ensure LLM doesn't break game tags (e.g., `{0}`, `\n`).
* [ ] **Prompt Templates:** Allow users to customize the LLM prompt per project.

---

## 4. Database / Persistence

Tasks about the local database schema and storage.

* [ ] **Schema Update:** Add `provider_id` and `remote_id` to the segments table.
* [ ] **Translation Memory:** Index successfully "Verified" translations for local reuse.
* [ ] **History Tracking:** Log changes per segment to allow local rollbacks.

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
