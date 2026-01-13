# Style Guide — Typing and ORM Queries

## Type-checking and SQLModel/SQLAlchemy conventions

* Prefer runtime correctness over static typing.
* Don’t rewrite ORM expressions purely for the type checker.
* Allow `# type: ignore[attr-defined]` when `__table__` or runtime attributes are involved.
* `ColumnElement` annotations are optional; use them only when they improve clarity.
* Never replace ORM calls like `.like()`, `.desc()`, or `.is_()` with string-based logic, as doing so bypasses the ORM's SQL escaping and can introduce security vulnerabilities.
