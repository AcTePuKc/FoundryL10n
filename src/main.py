import sys
from pathlib import Path

# --- THE HERO EXE BOOTSTRAPPER ---
# We use getattr to avoid Pylance/Linter errors regarding _MEIPASS
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
from core.engine import TranslationEngine
from core.parser import FoundryParser, TranslationSegment
from services.resource_service import ResourceLoader
from services.llm_service import LLMService

# Initialize Typer
app = typer.Typer(help="FoundryL10n: Professional Local-First Game Translator")

@app.callback()
def main():
    """Ensure the database is initialized before any command runs."""
    init_db()

@app.command(name="gui")
def launch_gui():
    """Launch the graphical interface (PySide6)."""
    try:
        from ui.main_window import run_gui
        run_gui()
    except Exception as e:
        print(f"[red]CRITICAL ERROR: Could not load GUI components.[/red]")
        print(f"Details: {e}")
        input("Press Enter to close...")

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
    
    # FIXED: Now passing paths to the loader
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
    
    # FIXED: Now passing paths to the loader
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