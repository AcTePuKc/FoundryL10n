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
        print(f"[yellow]Warning:[/yellow] Theme file not found: {theme_path}")
        return

    qss_text = theme_path.read_text(encoding="utf-8")

    app = QApplication.instance()
    if app is None:
        raise RuntimeError("QApplication instance not initialized.")

    # Tell the type checker this is a QApplication, not just QCoreApplication
    qt_app = cast(QApplication, app)
    qt_app.setStyleSheet(qss_text)

def get_available_themes() -> list[str]:
    theme_dir = base_path / "resources" / "themes"
    if not theme_dir.exists():
        return ["dark"]
    return sorted({theme.stem for theme in theme_dir.glob("*.qss")})

# Initialize Typer
app = typer.Typer(help="FoundryL10n: Professional Local-First Game Translator")

@app.callback()
def main():
    """Ensure the database is initialized before any command runs."""
    init_db()

@app.command(name="gui")
def launch_gui():
    """Launch the graphical interface with the configured theme."""
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

@app.command(name="file")
def translate_file(
    path: str = typer.Argument(..., help="The TSV file to translate"),
    lang: str = typer.Option("Bulgarian", "--lang", "-l"),
    model: str = typer.Option("qwen2.5:7b", "--model", "-m", help="Ollama model to use"),
    glossary: str = typer.Option("glossary.tsv", "--glossary", "-g"),
    style: str = typer.Option("style.md", "--style", "-s")
):
    """Translate a TSV file via CLI."""
    loader = ResourceLoader()
    parser = FoundryParser()
    
    llm_service = LLMService(model_name=model)
    engine = TranslationEngine(llm_service)
    
    glossary_content = loader.load_glossary(glossary)
    style_content = loader.load_style_guide(style)
    
    input_path = Path(path)
    if not input_path.exists():
        print(f"[red]Error: File '{path}' not found.[/red]")
        raise typer.Exit(code=1)
        
    segments = parser.parse_tsv(input_path)
    
    print(f"[bold cyan]Found {len(segments)} segments. Using model: {model}[/bold cyan]")
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        transient=False,
    ) as progress:
        task = progress.add_task(f"Translating to {lang}...", total=len(segments))
        for seg in segments:
            engine.run_translation([seg], lang, glossary=glossary_content, style=style_content, temp=0.1)
            progress.advance(task)

    output_path = Path("out") / lang / input_path.name
    parser.save_tsv(segments, output_path)
    print(f"\n[bold green]✔ Done![/bold green] Results saved to: [yellow]{output_path}[/yellow]")

@app.command(name="text")
def translate_text(
    content: str = typer.Argument(..., help="Text string to translate"),
    lang: str = typer.Option("Bulgarian", "--lang", "-l"),
    model: str = typer.Option("qwen2.5:7b", "--model", "-m"),
    glossary: str = typer.Option("glossary.tsv", "--glossary", "-g"),
    style: str = typer.Option("style.md", "--style", "-s")
):
    """Quickly translate a single string via CLI."""
    loader = ResourceLoader()
    llm_service = LLMService(model_name=model)
    engine = TranslationEngine(llm_service)
    
    glossary_content = loader.load_glossary(glossary)
    style_content = loader.load_style_guide(style)
    
    seg = TranslationSegment("CLI_TEST", content)
    engine.run_translation([seg], lang, glossary=glossary_content, style=style_content)
    
    print(f"\n[bold green]Original:[/bold green] {content}")
    print(f"[bold blue]Result:[/bold blue] {seg.translation}")

if __name__ == "__main__":
    if len(sys.argv) == 1:
        sys.argv.append("gui")
        
    try:
        app()
    except Exception as e:
        import traceback
        print("\n" + "="*50)
        print("CRITICAL ERROR:")
        traceback.print_exc()
        print("="*50)
        input("\nPress Enter to exit...")
