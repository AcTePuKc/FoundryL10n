import sys
import os
from pathlib import Path
import ctypes
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
from typing import cast

import typer
from rich import print
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, MofNCompleteColumn

# Modular Imports
from core.database import init_db
from core.engine import TranslationEngine
from core.i18n import I18N
from core.parser import FoundryParser, TranslationSegment
from services.resource_service import ResourceLoader
from services.llm_service import LLMService
from PySide6.QtCore import Qt, QSettings
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
    Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
)

def load_theme(theme_name: str) -> None:
    theme_path = base_path / "resources" / "themes" / f"{theme_name}.qss"
    if not theme_path.exists():
        print(I18N.t("cli_theme_missing_warning").format(theme_path=theme_path))
        return

    qss_text = theme_path.read_text(encoding="utf-8")

    app = QApplication.instance()
    if app is None:
        raise RuntimeError(I18N.t("cli_qapp_missing_error"))

    # Tell the type checker this is a QApplication, not just QCoreApplication
    qt_app = cast(QApplication, app)
    qt_app.setStyleSheet(qss_text)

def get_available_themes() -> list[str]:
    theme_dir = base_path / "resources" / "themes"
    if not theme_dir.exists():
        return ["dark"]
    return sorted({theme.stem for theme in theme_dir.glob("*.qss")})

# Initialize Typer
app = typer.Typer(help=I18N.t("cli_app_help"))

@app.callback()
def main():
    init_db()

@app.command(name="gui", help=I18N.t("cli_gui_help"))
def launch_gui():
    from PySide6.QtWidgets import QApplication
    from ui.main_window import FoundryGUI
    
    qt_app = QApplication(sys.argv)
    
    settings = QSettings("FoundryL10n", "TranslatorApp")
    theme_name = str(settings.value("ui_theme", "dark"))
    if theme_name not in get_available_themes():
        theme_name = "dark"
    load_theme(theme_name)
    
    window = FoundryGUI()
    window.show()
    sys.exit(qt_app.exec())

@app.command(name="file", help=I18N.t("cli_file_help"))
def translate_file(
    path: str = typer.Argument(..., help=I18N.t("cli_arg_file")),
    lang: str = typer.Option("Bulgarian", "--lang", "-l"),
    model: str = typer.Option("qwen2.5:7b", "--model", "-m", help=I18N.t("cli_opt_model_help")),
    glossary: str = typer.Option("glossary.tsv", "--glossary", "-g"),
    style: str = typer.Option("style.md", "--style", "-s")
):
    loader = ResourceLoader()
    parser = FoundryParser()
    
    llm_service = LLMService(model_name=model)
    engine = TranslationEngine(llm_service)
    
    glossary_content = loader.load_glossary(glossary)
    style_content = loader.load_style_guide(style)
    
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
        for seg in segments:
            engine.run_translation([seg], lang, glossary=glossary_content, style=style_content, temp=0.1)
            progress.advance(task)

    output_path = Path("out") / lang / input_path.name
    parser.save_tsv(segments, output_path)
    print(I18N.t("cli_done_results").format(output_path=output_path))

@app.command(name="text", help=I18N.t("cli_text_help"))
def translate_text(
    content: str = typer.Argument(..., help=I18N.t("cli_arg_text")),
    lang: str = typer.Option("Bulgarian", "--lang", "-l"),
    model: str = typer.Option("qwen2.5:7b", "--model", "-m"),
    glossary: str = typer.Option("glossary.tsv", "--glossary", "-g"),
    style: str = typer.Option("style.md", "--style", "-s")
):
    loader = ResourceLoader()
    llm_service = LLMService(model_name=model)
    engine = TranslationEngine(llm_service)
    
    glossary_content = loader.load_glossary(glossary)
    style_content = loader.load_style_guide(style)
    
    seg = TranslationSegment("CLI_TEST", content)
    engine.run_translation([seg], lang, glossary=glossary_content, style=style_content)
    
    print(I18N.t("cli_original_label").format(content=content))
    print(I18N.t("cli_result_label").format(result=seg.translation))

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
