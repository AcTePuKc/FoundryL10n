# FoundryL10n

FoundryL10n is a local-first translation workstation for narrative-heavy games. It blends a PySide6 desktop UI with a Typer-powered CLI, uses Ollama-hosted language models for machine translation, and keeps a persistent translation memory so your work never gets lost.

## Table of Contents

- [Key Features](#key-features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Usage](#usage)
  - [CLI](#cli)
  - [GUI](#gui)
  - [Workstation tab](#workstation-tab)
  - [Editor panel](#editor-panel)
  - [Integrity report tab](#integrity-report-tab)
  - [Settings tab](#settings-tab)
- [Project Structure](#project-structure)
- [Provider Integrations](#provider-integrations)
- [Translation Memory & Caching](#translation-memory--caching)
- [Development](#development)
  - [Style Guide](#style-guide)
  - [Dev Notes](#dev-notes)
- [Contributing](#contributing)

## Key Features

- **Dual Workflows** – Launch the PySide6 workstation (`python main.py gui`) or run fully headless TSV jobs from the Typer CLI.
- **Translation Memory & Recovery** – Rehydrates the table with previous translations, verification flags, locks, and AI drafts stored in `foundry_memory.db`.
- **Bulk Translation Pipeline** – Fire off long-running batches from the GUI or CLI, with live progress, pause/stop controls, and automatic draft restoration.
- **Placeholder Safety** – Masks XML tags, bracketed actions, numeric tokens, and other fragile placeholders before the LLM sees them.
- **Guided Prompts** – Blend glossary/style/forbidden lists with configurable prompt templates and temperature control per profile.
- **Productivity Tooling** – Search & filter rows, bulk-verify, run find/replace, export verified lines to a glossary, and surface fuzzy matches plus history for each entry.
- **Integrity & QA** – Dedicated audit tab to flag inconsistent translations across projects, with one-click normalization back into the database.
- **Local-First** – Everything (translations, profiles, memory) remains on disk; the only model calls are to your local Ollama host.

## Requirements

- Python 3.11+
- [Ollama](https://ollama.com/) running locally with at least one chat-capable model (default: `qwen2.5:7b`)
- Windows, macOS, or Linux desktop environment

Optional but recommended:

- `uv` for dependency management (a `uv.lock` is provided)
- `pytest` for local development checks

## Installation

1. **Create a virtual environment**

   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows use: .venv\Scripts\activate
   ```

2. **Install dependencies**

   ```bash
   pip install -r requirements.txt
   ```

   or, with `uv`:

   ```bash
   uv sync
   ```

3. **Prepare Ollama**

   ```bash
   ollama pull qwen2.5:7b
   ```

   Adjust the model name in the CLI/GUI settings if you use a different one.

   3.1 **"Best" Bulgarian Model so far**

      ```bash
      ollama pull s_emanuilov/BgGPT-v1.0:9b
      ```

      Feel free to change to `s_emanuilov/BgGPT-v1.0:2.6b` or `s_emanuilov/BgGPT-v1.0:27b` or any other hit search and type `bggpt` depending on your hardware capabilities.

4. **Hit refresh models in the GUI settings after pulling new ones.**

## Usage

### CLI

The entry point is `python main.py`. Running with no arguments will launch the GUI. The Typer CLI exposes the following commands:

| Command | Description |
| --- | --- |
| `python main.py gui` | Starts the PySide6 desktop interface. |
| `python main.py file <path>` | Translates a TSV file and saves the result to `out/<language>/<filename>`. |
| `python main.py text "Your line"` | Quick one-off translation of a text string. |

Common options:

- `--lang / -l` – Target language (default: `Bulgarian`).
- `--model / -m` – Ollama model to use (default: `qwen2.5:7b`).
- `--glossary / -g` – Path to a TSV/CSV glossary file.
- `--style / -s` – Path to a Markdown style guide.
- `--forbidden / -f` – Path to a forbidden-terms text file (one per line).
- `--project / -p` – Project name to load the matching prompt template from settings.

Example:

```bash
python main.py file dialogue.tsv --lang "French" --glossary profiles/french_glossary.tsv --style profiles/french_style.md
```

### GUI

The workstation UI is organized into three feature-rich tabs.

#### Workstation tab

- Import TSV files, instantly restoring saved translations, verification states, locks, and AI drafts from the memory database.
- Spreadsheet-like table with row filters (search text, “only errors”), bulk selection, and a right-click menu for quick verify/skip/clear actions.
- Kick off or halt bulk translation runs that stream updates row-by-row, respecting glossary/style guidance and placeholder shielding.
- “Follow” toggle keeps the view in sync with bulk translation progress, while **Focus: Table** hides auxiliary widgets for a distraction-free layout.
- Context menu shortcuts for find & replace across the file and exporting all verified rows to a glossary TSV.
- Live counters and a progress bar showing verified, QA, risk, error, conflict, pending, and locked states.

#### Editor panel

- Side-by-side source, AI draft, and editable translation fields with configurable font size and keyboard shortcuts (Ctrl+Enter to save & advance).
- Fuzzy match suggestions powered by the translation engine, with one-click insertion and a scrollable history of past revisions for each row.
- Verification, skip, rollback, and navigation controls, plus the ability to toggle the entire panel or scroll it independently when the window is compact.

#### Integrity report tab

- Runs database-wide consistency checks to surface entries where a source string has multiple translations.
- Presents conflicts in a table with per-row “Normalize” actions that let you pick the canonical translation and push it back to SQLite.
- Integrates with the Workstation tab, re-highlighting rows with conflicts after each audit.

#### Settings tab

- Manage project profiles: set target language, project name, save/load presets, and refresh the list of Ollama models.
- Adjust LLM parameters (model, temperature, timeout), font size, and strict-tag mode.
- Configure resource paths (glossary, style guide, forbidden terms) via quick file pickers.
- Edit prompt templates directly, or pick from curated presets tailored for localization, tag surgery, or creative polish.
- Database utilities let you run global replace, purge unverified entries, clear tag mismatches, or wipe the entire memory for a project.

Launch the GUI with:

```bash
python main.py gui
```

## Project Structure

```bash
src/
├── core/           # Parsing, masking, translation engine, database helpers
├── services/       # LLM/Ollama integration and resource loaders
├── ui/             # PySide6 windows, tabs, and worker threads
└── main.py         # CLI entry point and bootstrapping logic
```

Supporting assets:

- `glossary.tsv`, `dialogue.tsv` – Sample resources for testing
- `profiles/` – Saved settings and presets
- `foundry_memory.db` – SQLite translation memory (auto-created)

## Provider Integrations

Provider integration modules live in `src/plugins` as JSON configs that describe how to authenticate with and talk to external translation sites. This keeps remote platform details (endpoints, headers, field mapping, auth inputs) packaged as data rather than hardcoded dependencies.

The app reads the active provider config at runtime and uses the generic integration client to fetch or push segments. UI actions communicate through the provider configuration, so no direct imports of provider SDKs or site-specific code are required in the core/UI layers.

## Translation Memory & Caching

- Every translation is hashed and stored in SQLite (`core/database.py`).
- Verified lines and “never translate” flags take precedence over new suggestions.
- Manual edits in the GUI or CLI are written back to the memory so reruns stay fast.

## Development

- Run linting or formatting tools as needed (none are enforced by default).
- Execute the automated tests (if/when added) with:

  ```bash
  pytest
  ```

- PyInstaller specs are provided (`FoundryL10n.spec`) for packaging desktop builds.

### Style Guide

Refer to the ORM/type-checking conventions in [docs/STYLE_GUIDE.md](docs/STYLE_GUIDE.md) when updating database queries or resolving Pylance typing issues.

### Dev Notes

<details>
<summary>Click to expand</summary>

- The mock server is **dev-only** and lives under `tools/` (or `dev/` if relocated).
- It is excluded from production/distribution builds.
- TODO: Update this note if the mock server location changes.
- Run it with:

  ```bash
  python tools/mock_server/mock_server.py --host 127.0.0.1 --port 8000
  ```
</details>

## Contributing

1. Fork the repository.
2. Create a feature branch.
3. Submit a pull request describing your changes.

Issues and feature ideas are welcome. Please include reproduction steps for bugs and screenshots or logs when possible.
