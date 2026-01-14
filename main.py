from pathlib import Path
import runpy
import sys

def main() -> None:
    entrypoint = Path(__file__).parent / "src" / "main.py"
    try:
        runpy.run_path(str(entrypoint), run_name="__main__")
    except FileNotFoundError:
        print("Error: src/main.py not found. Did you forget to create it?", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()