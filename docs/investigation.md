# FoundryL10n Audit Notes (src/)

## Scope
Focused on `src/ui`, `src/core`, and `src/services` for likely refactor hotspots, unused definitions, and prompt/template connectivity relevant to CAT workflows (segment navigation, QA markers, and tag safety).

## Likely refactor hotspots (CAT impact)
- **`src/ui/main_window.py`** — High-density coordinator: constructs widgets, owns signal wiring, context menus, translation flow, and DB persistence in one file. This is a refactor hotspot because UI behavior (segment workflow, QA statuses, and menu actions) is tightly coupled here. Any CAT UX change (navigation, verification, QA markers) will land in this module and should be done carefully to preserve keyboard-driven workflows and state flags.【F:src/ui/main_window.py†L40-L940】
- **`src/ui/settings_tab.py`** — Large multi-section form (general/translation/appearance/resources/prompt/tools). It’s a hotspot for future modularization, but current hookups look cohesive. Changes here can affect translator defaults, prompt behavior, and resource loading paths, so they should remain incremental.【F:src/ui/settings_tab.py†L18-L220】
- **`src/core/engine.py`** — Mixes translation orchestration, audit logic, and fuzzy match. It’s a hotspot because it drives segment state and QA heuristics; any refactor must preserve verification flags, tag safety, and risk indicators used by the CAT UI.【F:src/core/engine.py†L1-L215】
- **`src/services/llm_service.py`** — Prompt assembly + response cleanup + placeholder validation. It’s a hotspot because prompt templates and post-processing directly affect tag safety and translation quality. CAT workflow depends on preserving placeholders and avoiding “chatty” output.【F:src/services/llm_service.py†L1-L162】

## Static analysis report (ruff: F401/F841/F811)
Command used: `ruff check src --select F401,F841,F811`

Findings:
- `src/core/masker.py`: `List` and `Tuple` imports are unused. **Recommendation:** safe to remove (no CAT impact).【F:src/core/masker.py†L1-L3】
- `src/main.py`: `except Exception as e` binds `e` but never uses it. **Recommendation:** safe to remove binding (`except Exception:`) without behavior change.【F:src/main.py†L143-L146】

## UI event hookup review (CAT workflow)
### `src/ui/main_window.py`
- **Translation tab controls** (open/search/filter/toggle editor/zen) are connected and reachable. These are key to rapid segment filtering and ergonomics.【F:src/ui/main_window.py†L103-L135】
- **Editor panel actions** (translate/rollback/save/prev/next/history double-click) are wired. These preserve keyboard-forward editing flow and quick history restore.【F:src/ui/main_window.py†L79-L188】
- **Context menu actions** are all attached to the table right-click (multi-row and single-row actions + global find/replace/export). This preserves low-friction QA workflows for bulk verify/skip/clear operations.【F:src/ui/main_window.py†L892-L939】

**Potential gap (keep or wire intentionally):**
- `EditorPanel.cb_verified` exists but has **no signal hookup** to update segment state when a user toggles it. As-is, the checkbox is only updated programmatically after saves; manual user toggling won’t persist. This is worth deciding: either wire it to a slot or disable it to avoid misleading UI. I left it unchanged because it might be intentional (verification is only set via save).【F:src/ui/editor_panel.py†L56-L69】【F:src/ui/main_window.py†L79-L188】

### `src/ui/settings_tab.py`
All controls are wired to handlers (profile save/load, model refresh, font size, theme, UI language, resource browse buttons, prompt reset, global replace/purge/clear/wipe). No missing signal hookups found.【F:src/ui/settings_tab.py†L57-L210】

## Prompt/template helpers (orphan checks)
- **Active settings prompts**: Settings tab provides templates (`prompt_default`, `prompt_template_technical`, `prompt_template_creative`), and LLM service falls back to `prompt_template_fallback` when `{source}` is missing. This is CAT-safe and consistent with tag-preservation rules.【F:src/ui/settings_tab.py†L231-L608】【F:src/services/llm_service.py†L62-L80】
- **Potentially orphaned UI module**: `src/ui/prompt_editor.py` defines a “Prompt Library” widget with its own template keys (`prompt_template_standard`, `prompt_template_tag_surgeon_pass2`, `prompt_template_narrative_polish`). It is **not referenced** by `main_window` or `settings_tab`, which suggests **unused but expected future feature**. If kept, it’s a reasonable placeholder for a richer prompt UI; removing it might drop planned functionality.【F:src/ui/prompt_editor.py†L1-L51】【F:src/ui/main_window.py†L60-L188】
- **Orphaned locale key**: `prompt_template_fallback_note` appears in locales but is unused in code. This is **unused and safe to remove**, unless a future UI wants to show prompt placeholder help text.【F:resources/locales.json†L328-L333】【F:src/services/llm_service.py†L62-L80】

## Unused definitions: CAT relevance & keep/remove notes
| Location | Definition | CAT relevance | Note | Recommendation |
| --- | --- | --- | --- | --- |
| `src/core/masker.py` | `typing.List`, `typing.Tuple` imports | None | Unused imports only. | **Safe to remove** (no CAT impact).【F:src/core/masker.py†L1-L3】 |
| `src/main.py` | `except Exception as e` | None | `e` is unused; behavior unchanged if removed. | **Safe to remove**.【F:src/main.py†L143-L146】 |
| `src/ui/prompt_editor.py` | `PromptEditor` widget | Potential future CAT UX | Not wired in current UI; likely intended for a richer prompt library. | **Keep for future feature** unless project scope says to remove unused UI modules.【F:src/ui/prompt_editor.py†L1-L51】 |
| `resources/locales.json` | `prompt_template_fallback_note` | None | Unused locale string. | **Safe to remove** unless a future UI needs it.【F:resources/locales.json†L328-L333】 |

## Deletion strategy (if desired)
If cleanups are approved, delete in small batches (one module at a time) and re-run static checks after each module to confirm no regressions.
