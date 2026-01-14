import csv
import subprocess
import sys
from pathlib import Path

MODEL = "bggpt-gemma-9b:latest"

def translate(text: str) -> str:
    prompt = f"Translate to Bulgarian. Preserve placeholders. Text:\n{text}\n"
    result = subprocess.run(
        ["ollama", "run", MODEL],
        input=prompt.encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout.decode("utf-8").strip()

def process_tsv(src: Path, dst: Path):
    with src.open("r", encoding="utf-8") as f_in, dst.open("w", encoding="utf-8", newline="") as f_out:
        reader = csv.DictReader(f_in, delimiter="\t")

        fieldnames = reader.fieldnames or ["key", "source", "translation"]
        writer = csv.DictWriter(f_out, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()

        for row in reader:
            src_text = row.get("source", "").strip()

            if not src_text:
                # no source → skip translation but preserve row
                row["translation"] = row.get("translation", "")
                writer.writerow(row)
                continue

            # translate
            row["translation"] = translate(src_text)
            writer.writerow(row)

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python translate_tsv.py input.tsv output.tsv")
        sys.exit(1)
    process_tsv(Path(sys.argv[1]), Path(sys.argv[2]))
