"""Run the merged branch suite against a fresh migrated PostgreSQL application DB.

BACKTEST_TEST_DATABASE_URL must point at a dedicated reserve_juggler_m2_test*
server database. Only this process's generated database is created/dropped.
Extra CLI arguments are passed unchanged to pytest. No shared DB is reset.
"""
import os
from pathlib import Path
import re
import subprocess
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT)]


def main():
    from sqlalchemy import create_engine
    from sqlalchemy.engine import make_url
    from sqlalchemy.orm import Session
    from app.data.organizer import OrganizerDatasetSource
    from app.persistence.migrations import apply_migrations
    from app.persistence.repositories import DatasetRepository

    url = make_url(os.environ["BACKTEST_TEST_DATABASE_URL"])
    if not (url.database or "").startswith("reserve_juggler_m2_test"):
        raise ValueError("A dedicated reserve_juggler_m2_test* database URL is required")
    name = "reserve_juggler_m2_test_bt_suite_" + uuid4().hex[:12]
    assert re.fullmatch(r"reserve_juggler_m2_test_bt_suite_[a-f0-9]{12}", name)
    admin = create_engine(url, isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.exec_driver_sql(f'CREATE DATABASE "{name}"')
    engine = create_engine(url.set(database=name))
    try:
        apply_migrations(engine)
        with Session(engine) as session, session.begin():
            DatasetRepository(session).store(OrganizerDatasetSource().load())
        task_env = dict(os.environ)
        task_env["DATABASE_URL"] = url.set(database=name, drivername="postgresql+psycopg2").render_as_string(hide_password=False)
        task_env["PERSISTENCE_TEST_DATABASE_URL"] = os.environ["BACKTEST_TEST_DATABASE_URL"]
        task_env["PYTHONDONTWRITEBYTECODE"] = "1"
        return subprocess.run([sys.executable,"-m","pytest",*sys.argv[1:]], env=task_env, cwd=ROOT).returncode
    finally:
        engine.dispose()
        with admin.connect() as connection:
            connection.exec_driver_sql(f'DROP DATABASE "{name}"')
        admin.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
