# FoundryL10n Audit Notes (src/)

## Scope
Focused on `src/ui`, `src/core`, and `src/services` for likely refactor hotspots, unused definitions, and prompt/template connectivity relevant to CAT workflows (segment navigation, QA markers, and tag safety).

## Likely refactor hotspots (CAT impact)
- **`src/ui/main_window.py`** — High-density coordinator: constructs widgets, owns signal wiring, context menus, translation flow, and DB persistence in one file. This is a refactor hotspot because UI behavior (segment workflow, QA statuses, and menu actions) is tightly coupled here. Any CAT UX change (navigation, verification, QA markers) will land in this module and should be done carefully to preserve keyboard-driven workflows and state flags.【F:src/ui/main_window.py†L40-L940】
- **`src/ui/settings_tab.py`** — Large multi-section form (general/translation/appearance/resources/prompt/tools). It’s a hotspot for future modularization, but current hookups look cohesive. Changes here can affect translator defaults, prompt behavior, and resource loading paths, so they should remain incremental.【F:src/ui/settings_tab.py†L18-L220】
- **`src/core/engine.py`** — Mixes translation orchestration, audit logic, and fuzzy match. It’s a hotspot because it drives segment state and QA heuristics; any refactor must preserve verification flags, tag safety, and risk indicators used by the CAT UI.【F:src/core/engine.py†L1-L215】
- **`src/services/llm_service.py`** — Prompt assembly + response cleanup + placeholder validation. It’s a hotspot because prompt templates and post-processing directly affect tag safety and translation quality. CAT workflow depends on preserving placeholders and avoiding “chatty” output.【F:src/services/llm_service.py†L1-L162】


## Planned Refactoring
- **Tag helper consolidation** — Tag insertion and placeholder handling should be consolidated to a single helper surface (menu + shortcuts + editor hooks) to avoid divergent behavior across panels. Treat this as an intentional refactor area rather than ad-hoc edits.

## Open UX proposals
- **Reverse Zen Mode (editor focus)** — Current Zen Mode is table-centric (hides the editor panel and expands the table). A complementary “reverse zen” would hide/minimize the table and expand the editor panel for deep editing, QA tag fixes, and keyboard-forward translation review. This preserves the existing Zen Mode while adding an editor-centric option for polishing workflows.
- **Tag insertion panel** — Add a lightweight panel or popover listing available tags/placeholders, with click-to-insert and keyboard insertion shortcuts. This should integrate with the same tag helper logic used by context menus so translators can insert tags without leaving the editor.
