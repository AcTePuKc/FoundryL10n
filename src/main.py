import sys
import os
from pathlib import Path
import ctypes
from typing import NamedTuple
try:
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("FoundryL10n.Workspace.V1")
except Exception:
    pass
os.environ["QT_LOGGING_RULES"] = "qt.text.font.db.warning=false"

# --- BOOTSTRAPPER ---
if getattr(sys, 'frozen', False):
    # PyInstaller temporary folder
    base_path = Path(getattr(sys, '_MEIPASS'))
    sys.path.append(str(base_path / "src"))
else:
    # Development mode
    base_path = Path(__file__).parent.parent
    sys.path.append(str(base_path / "src"))
import typer
from rich import print
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, MofNCompleteColumn

# Modular Imports
from core.database import init_db
from core.i18n import I18N
from core.parser import FoundryParser, TranslationSegment
from services.resource_service import ResourceLoader
from services.llm_service import LLMService
from services.plugin_loader import PluginLoader
from services.translation_service import run_batch_translation
from PySide6.QtCore import Qt, QSettings
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication
from ui.theme_helpers import get_available_themes, load_theme

QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
    Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
)

# Initialize Typer
app = typer.Typer(help=I18N.t("cli_app_help"))

ORG_NAME = "FoundryL10n"
APP_NAME = "TranslatorApp"


def _normalize_project_name(name: str) -> str:
    return name.strip() or "default"


def _prompt_settings_key(project_name: str) -> str:
    safe_name = _normalize_project_name(project_name)
    return f"prompt_templates/{safe_name}"


def _load_prompt_template(project_name: str) -> str:
    try:
        from PySide6.QtCore import QSettings
    except ImportError:
        return I18N.t("prompt_default")

    settings = QSettings(ORG_NAME, APP_NAME)
    key = _prompt_settings_key(project_name)
    if settings.contains(key):
        return str(settings.value(key))
    if settings.contains("custom_prompt"):
        legacy_prompt = str(settings.value("custom_prompt"))
        settings.setValue(key, legacy_prompt)
        settings.remove("custom_prompt")
        return legacy_prompt
    return I18N.t("prompt_default")


class CliResources(NamedTuple):
    glossary_content: str
    style_content: str
    forbidden_content: str
    project_name: str
    prompt_template: str


def _load_cli_resources(
    glossary_path: str,
    style_path: str,
    forbidden_path: str,
    project: str,
) -> CliResources:
    loader = ResourceLoader()
    glossary_content = loader.load_glossary(glossary_path)
    style_content = loader.load_style_guide(style_path)
    forbidden_content = loader.load_forbidden_words(forbidden_path)
    project_name = _normalize_project_name(project)
    prompt_template = _load_prompt_template(project_name)
    return CliResources(
        glossary_content,
        style_content,
        forbidden_content,
        project_name,
        prompt_template,
    )

@app.callback()
def main():
    """Ensure the database is initialized before any command runs."""
    init_db()

@app.command(name="gui", help=I18N.t("cli_gui_help"))
def launch_gui():
    """Launch the graphical interface with the configured theme."""
    from ui.main_window import FoundryGUI
    
    qt_app = QApplication(sys.argv)

    plugin_registry = PluginLoader().load_registry()
    
    settings = QSettings("FoundryL10n", "TranslatorApp")
    theme_name = str(settings.value("ui_theme", "dark"))
    if theme_name not in get_available_themes():
        theme_name = "dark"
    load_theme(theme_name)
    
    window = FoundryGUI(plugin_registry=plugin_registry)
    window.show()
    sys.exit(qt_app.exec())

@app.command(name="file", help=I18N.t("cli_file_help"))
def translate_file(
    path: str = typer.Argument(..., help=I18N.t("cli_arg_file")),
    lang: str = typer.Option("Bulgarian", "--lang", "-l"),
    model: str = typer.Option("qwen2.5:7b", "--model", "-m", help=I18N.t("cli_opt_model_help")),
    timeout: float | None = typer.Option(
        None,
        "--timeout",
        help=I18N.t("cli_opt_timeout_help"),
    ),
    glossary: str = typer.Option("glossary.tsv", "--glossary", "-g"),
    style: str = typer.Option("style.md", "--style", "-s"),
    forbidden: str = typer.Option("forbidden.txt", "--forbidden", "-f"),
    project: str = typer.Option("default", "--project", "-p"),
    out: str | None = typer.Option(None, "--out", "-o"),
):
    """Translate a TSV file via CLI."""
    parser = FoundryParser()
    
    llm_service = LLMService(model_name=model, timeout=timeout)
    (
        glossary_content,
        style_content,
        forbidden_content,
        project_name,
        prompt_template,
    ) = _load_cli_resources(glossary, style, forbidden, project)
    
    input_path = Path(path)
    if not input_path.exists():
        print(I18N.t("cli_file_missing_error").format(path=path))
        raise typer.Exit(code=1)
        
    segments = parser.parse_tsv(input_path)
    
    print(I18N.t("cli_found_segments").format(count=len(segments), model=model))
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        transient=False,
    ) as progress:
        task = progress.add_task(
            I18N.t("cli_translating_to").format(lang=lang),
            total=len(segments),
        )
        run_batch_translation(
            segments,
            lang,
            llm_service,
            glossary=glossary_content,
            style=style_content,
            forbidden=forbidden_content,
            temp=0.1,
            prompt_template=prompt_template,
            project_name=project_name,
            progress_callback=lambda _count: progress.advance(task),
        )

    output_path = Path(out) if out else Path("out") / lang / input_path.name
    parser.save_tsv(segments, output_path)
    print(I18N.t("cli_done_results").format(output_path=output_path))

@app.command(name="text", help=I18N.t("cli_text_help"))
def translate_text(
    content: str = typer.Argument(..., help=I18N.t("cli_arg_text")),
    lang: str = typer.Option("Bulgarian", "--lang", "-l"),
    model: str = typer.Option("qwen2.5:7b", "--model", "-m"),
    timeout: float | None = typer.Option(
        None,
        "--timeout",
        help=I18N.t("cli_opt_timeout_help"),
    ),
    glossary: str = typer.Option("glossary.tsv", "--glossary", "-g"),
    style: str = typer.Option("style.md", "--style", "-s"),
    forbidden: str = typer.Option("forbidden.txt", "--forbidden", "-f"),
    project: str = typer.Option("default", "--project", "-p"),
):
    """Quickly translate a single string via CLI."""
    llm_service = LLMService(model_name=model, timeout=timeout)
    (
        glossary_content,
        style_content,
        forbidden_content,
        project_name,
        prompt_template,
    ) = _load_cli_resources(glossary, style, forbidden, project)
    
    seg = TranslationSegment("CLI_TEST", content)
    run_batch_translation(
        [seg],
        lang,
        llm_service,
        glossary=glossary_content,
        style=style_content,
        forbidden=forbidden_content,
        prompt_template=prompt_template,
        project_name=project_name,
    )
    
    print(I18N.t("cli_original_label").format(content=content))
    print(I18N.t("cli_result_label").format(result=seg.translation))


main.__doc__ = I18N.t("cli_main_doc")
launch_gui.__doc__ = I18N.t("cli_gui_doc")
translate_file.__doc__ = I18N.t("cli_file_doc")
translate_text.__doc__ = I18N.t("cli_text_doc")

if __name__ == "__main__":
    if len(sys.argv) == 1:
        sys.argv.append("gui")
        
    try:
        app()
    except Exception as e:
        import traceback
        print("\n" + "="*50)
        print(I18N.t("cli_critical_error"))
        traceback.print_exc()
        print("="*50)
        input(I18N.t("cli_press_enter_exit"))
