import importlib
from pathlib import Path
from types import ModuleType
from typing import Optional
from core.database import TranslationRecord, engine

import typer
from rich import print
from sqlmodel import Session, select
tomllib: ModuleType
try:
    tomllib = importlib.import_module("tomllib")
except ModuleNotFoundError:
    # For Python < 3.11, requires `pip install tomli`
    tomllib = importlib.import_module("tomli")
    

app = typer.Typer(help="Scan the translation memory for conflicting targets per source.")


def _load_active_project_name(config_path: Path = Path("foundry.toml")) -> Optional[str]:
    if not config_path.exists():
        return None
    try:
        data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError:
        return None
    project_config = data.get("project")
    name = project_config.get("name") if isinstance(project_config, dict) else None
    return name if isinstance(name, str) and name.strip() else None


def _resolve_project_name(project: Optional[str], project_id: Optional[str]) -> str:
    if project and project.strip():
        return project
    if project_id and project_id.strip():
        return project_id
    active = _load_active_project_name()
    if active:
        return active
    return "default"


@app.command("report")
def report_conflicts(
    project: Optional[str] = typer.Option(
        None,
        "--project",
        "-p",
        help="Project name scope (defaults to active project or 'default').",
    ),
    project_id: Optional[str] = typer.Option(
        None,
        "--project-id",
        help="Alias for --project.",
    ),
    lang: Optional[str] = typer.Option(
        None,
        "--lang",
        "-l",
        help="Filter by target language.",
    ),
    target_field: str = typer.Option(
        "translation",
        "--target-field",
        "-t",
        help="Which field to compare: translation or ai_draft.",
    ),
    status: str = typer.Option(
        "all",
        "--status",
        help="Filter by verification status: all, verified, unverified.",
    ),
    verified_only: bool = typer.Option(
        False,
        "--verified-only",
        help="Shortcut for --status=verified.",
    ),
    unverified_only: bool = typer.Option(
        False,
        "--unverified-only",
        help="Shortcut for --status=unverified.",
    ),
    include_empty: bool = typer.Option(
        False,
        "--include-empty",
        help="Include empty target values in the comparison.",
    ),
) -> None:
    """Emit a grouped report of source strings with conflicting targets."""
    project_name = _resolve_project_name(project, project_id)

    normalized_target = target_field.strip().lower()
    if normalized_target not in {"translation", "ai_draft"}:
        raise typer.BadParameter("target-field must be 'translation' or 'ai_draft'.")

    status_value = status.strip().lower()
    if verified_only and unverified_only:
        raise typer.BadParameter("Choose only one of --verified-only or --unverified-only.")
    if (verified_only or unverified_only) and status.strip().lower() != "all":
        raise typer.BadParameter("Cannot use --status with --verified-only or --unverified-only.")
    if verified_only:
        status_value = "verified"
    elif unverified_only:
        status_value = "unverified"
    if status_value not in {"all", "verified", "unverified"}:
        raise typer.BadParameter("status must be one of: all, verified, unverified.")

    target_col = (
        TranslationRecord.translation
        if normalized_target == "translation"
        else TranslationRecord.ai_draft
    )

    statement = select(
        TranslationRecord.id,
        TranslationRecord.source_text,
        target_col,
        TranslationRecord.segment_key,
    ).where(TranslationRecord.project_name == project_name)

    if lang:
        statement = statement.where(TranslationRecord.target_lang == lang)
    if status_value == "verified":
        statement = statement.where(TranslationRecord.__table__.c.is_verified.is_(True))
    if status_value == "unverified":
        statement = statement.where(TranslationRecord.__table__.c.is_verified.is_(False))

    conflict_map: dict[str, dict[str, list[str]]] = {}

    with Session(engine) as session:
        results = session.exec(statement)

    for record_id, source_text, target_value, segment_key in results:
        if not source_text:
            continue
        value = target_value or ""
        if not include_empty and not value.strip():
            continue
        target_label = value.strip() if value.strip() else "<empty>"
        source_bucket = conflict_map.setdefault(source_text, {})
        target_bucket = source_bucket.setdefault(target_label, [])
        segment_label = f"{record_id}" if record_id is not None else segment_key
        target_bucket.append(str(segment_label))

    conflicts = {
        source: targets
        for source, targets in conflict_map.items()
        if len(targets) > 1
    }

    print(
        f"[bold]Consistency check[/bold] project='{project_name}'"
        f" lang='{lang or 'any'}' field='{normalized_target}'"
        f" status='{status_value}'"
    )

    if not conflicts:
        print("[green]No conflicts found.[/green]")
        raise typer.Exit(code=0)

    print(f"[yellow]Found {len(conflicts)} conflicting sources.[/yellow]")
    for source in sorted(conflicts.keys()):
        print(f"\n[bold]Source:[/bold] {source}")
        for target, ids in sorted(conflicts[source].items()):
            joined_ids = ", ".join(sorted(ids, key=str))
            print(f"  - [cyan]{target}[/cyan] -> IDs: {joined_ids}")


if __name__ == "__main__":
    app()
