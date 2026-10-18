"""Explicit, transactional PostgreSQL migrations; never silently use SQLite."""

import hashlib
from pathlib import Path

from sqlalchemy import create_engine, text


MIGRATION_DIRECTORY = Path(__file__).resolve().parents[3] / "database" / "migrations"


def apply_migrations(engine, directory=MIGRATION_DIRECTORY):
    if engine.dialect.name != "postgresql":
        raise ValueError("Treasury migrations require PostgreSQL")
    applied = []
    with engine.begin() as connection:
        connection.execute(text("SELECT pg_advisory_xact_lock(724319201)"))
        connection.exec_driver_sql("""CREATE TABLE IF NOT EXISTS public.reserve_juggler_migrations (
            name TEXT PRIMARY KEY, sha256 VARCHAR(64) NOT NULL,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
        previous = dict(connection.execute(text("SELECT name, sha256 FROM public.reserve_juggler_migrations")).all())
        for path in sorted(directory.glob("[0-9][0-9][0-9]_*.sql")):
            script = path.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
            digest = hashlib.sha256(script.encode("utf-8")).hexdigest()
            if path.name in previous:
                if previous[path.name] != digest:
                    raise ValueError(f"Applied migration was modified: {path.name}")
                continue
            connection.exec_driver_sql(script, execution_options={"no_parameters": True})
            connection.execute(text("INSERT INTO public.reserve_juggler_migrations(name, sha256) VALUES (:name, :hash)"),
                               {"name": path.name, "hash": digest})
            applied.append(path.name)
    return tuple(applied)


if __name__ == "__main__":
    from app.config import settings
    engine = create_engine(settings.DATABASE_URL)
    print("Applied:", apply_migrations(engine))
