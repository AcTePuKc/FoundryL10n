from pathlib import Path
import runpy


def main() -> None:
    entrypoint = Path(__file__).parent / "src" / "main.py"
    runpy.run_path(str(entrypoint), run_name="__main__")


if __name__ == "__main__":
    main()
