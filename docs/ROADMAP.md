# FoundryL10n Roadmap

This document describes the high-level evolution of FoundryL10n as a modular CAT workstation.

## 0.2 – Local CAT Refinement

**Focus:** Making the workstation reliable for individual offline use.

* [ ] **Core Workflow:** Stabilize segment navigation and auto-save.
* [ ] **Editor UX:** Implement focus modes and keyboard shortcuts ( to confirm).
* [ ] **LLM Orchestration:** Improve local Ollama/LM Studio prompt templates for game-specific context.

## 0.3 – The Plugin Engine (Infrastructure)

**Focus:** Building the "Bridge" that allows external website integrations.

* [ ] **Provider Interface:** Define the standard for how the app talks to external APIs.
* [ ] **Plugin Loader:** Support loading `.json` or `.js` provider configs from a local `/plugins` folder.
* [ ] **GitHub Sync:** Implement auto-updating of the `/plugins` folder from the central repository.
* [ ] **Secure Vault:** Implement encrypted local storage for user API tokens and credentials.

## 0.4 – First Integration: AdventurersBG (Phase 1)

**Focus:** Proving the system works with a live community platform.

* [ ] **Official Provider:** Release the `adventurers_bg.json` plugin.
* [ ] **API Sync:** Implement Login -> Fetch Page -> Push Suggestion workflow.
* [ ] **Conflict Management:** Visual UI for when a server string has changed compared to the local draft.
* [ ] **TSV Export:** Dedicated export profile for game engines used on AdventurersBG.

## 0.5 – QA & Translation Memory

**Focus:** Quality control and consistency across large projects.

* [ ] **Tag Safety:** Automated validation to ensure LLMs don't corrupt game tags (e.g., `%s`, `{id}`).
* [ ] **Local TM:** Searchable database of previous translations to suggest "matches" for new segments.
* [ ] **Batch Processing:** Ability to "Submit All Verified" segments on a page in one click.

## 1.0 – Community Expansion

**Focus:** Scaling the ecosystem.

* [ ] **Multi-Provider Support:** Open documentation for other communities to write their own plugins.
* [ ] **Advanced Mapping:** Allow plugins to define custom UI fields (e.g., "Character Gender" or "Max Length").
* [ ] **Quality Dashboard:** UI for tracking progress, LLM usage stats, and accuracy.
