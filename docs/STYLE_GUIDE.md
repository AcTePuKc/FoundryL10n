# Style Guide

## Type-checking and ORM notes

When addressing type checker warnings in SQLModel/SQLAlchemy code, follow these rules:

* prefer runtime correctness,
* don’t rewrite ORM for type checker,
* allow `# type: ignore[attr-defined]`,
* optional `ColumnElement` annotations,
* never replace `like/desc/is_` with string logic.
