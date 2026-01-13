# Style Guide — Typing and ORM Queries

## Type-checking and SQLModel/SQLAlchemy conventions

* Prefer runtime correctness over static typing.
* Don’t rewrite ORM expressions purely for the type checker.
* Allow `# type: ignore[attr-defined]` when `__table__` or runtime attributes are involved.
* `ColumnElement` annotations are optional; use them only when they improve clarity.
* Never replace `like`/`desc`/`is_` ORM calls with string logic.
