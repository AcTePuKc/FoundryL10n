# FoundryL10n

FoundryL10n is a local-first translation workstation for narrative-heavy games. It blends a PySide6 desktop UI with a Typer-powered CLI, uses Ollama-hosted language models for machine translation, and keeps a persistent translation memory so your work never gets lost.

## Key Features

- **Two Workflows** – Launch an interactive desktop UI (`foundryl10n gui`) or drive bulk translation from the command line.
- **Placeholder Safety** – Automatically masks XML tags, bracketed actions, Python-style `%s/%d` formatters, and other tokens so LLMs won’t break your scripts.
- **Translation Memory** – Stores every suggestion in `foundry_memory.db`, including human approvals and “never translate” decisions.
- **Glossary & Style Guidance** – Optional TSV/CSV glossary, Markdown style guides, and forbidden word lists are merged into each prompt.
- **Progress Tracking** – Rich-powered CLI progress bars and GUI stats help you see what’s translated, pending, or needs review.
- **Local-First** – All assets (translations, glossaries, memory) stay on disk; nothing is sent to remote services beyond your Ollama host.

## Requirements

- Python 3.13+
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

Example:
```bash
python main.py file dialogue.tsv --lang "French" --glossary profiles/french_glossary.tsv --style profiles/french_style.md
```

### GUI

`foundryl10n` ships with a workstation UI tailored for translators:

- **Workstation Tab** – Load TSV files, view translation states, apply filters, and inspect AI “thoughts”.
- **Editor Panel** – Apply manual edits, mark lines as verified, or flag entries as “never translate”.
- **Bulk Translation** – Run the LLM against the current file, masking placeholders and honoring glossary/style guidance.
- **Settings Tab** – Configure model name, temperature, target language, font sizes, and default resource paths.

To launch:
```bash
python main.py gui
```

## Project Structure

```
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

## Contributing

1. Fork the repository.
2. Create a feature branch.
3. Submit a pull request describing your changes.

Issues and feature ideas are welcome. Please include reproduction steps for bugs and screenshots or logs when possible.
