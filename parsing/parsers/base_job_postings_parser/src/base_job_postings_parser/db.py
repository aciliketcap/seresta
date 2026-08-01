"""SQLAlchemy bootstrap helpers shared by all job posting parsers.

This module owns the declarative ``Base`` so that all ORM classes across
``base_job_postings_parser`` and apps derived from it register with a single
``MetaData`` instance.

Connection info is split between:

- environment variables for non-secret configuration (host, port, db,
  sslmode);
- a JSON file in ``$SECRETS_DIR`` for credentials (user, password).
"""

import json
import os
from pathlib import Path

from sqlalchemy import URL, Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    """Declarative base for every ORM class in this project."""


PG_CREDENTIALS_FILE = "postgres.json"


def read_pg_credentials(secrets_dir: Path) -> tuple[str, str]:
    """Load Postgres user + password from ``secrets_dir/postgres.json``."""
    creds_path = secrets_dir / PG_CREDENTIALS_FILE
    if not creds_path.is_file():
        raise FileNotFoundError(
            f"Postgres credentials file not found at {creds_path}. "
            f"Create it with keys 'user' and 'password'."
        )
    with creds_path.open() as f:
        data = json.load(f)
    try:
        return data["user"], data["password"]
    except KeyError as err:
        raise KeyError(
            f"{creds_path} is missing required key {err!s}; "
            f"expected both 'user' and 'password'."
        ) from err


def build_engine_from_env(secrets_dir: Path) -> Engine:
    """Build a SQLAlchemy ``Engine`` from env vars + the secrets file.

    Required env vars: ``POSTGRES_HOST``, ``POSTGRES_DB``.
    Optional env vars: ``POSTGRES_PORT`` (default 5432), ``POSTGRES_SSLMODE``
    (default ``disable``).
    """
    try:
        host = os.environ["POSTGRES_HOST"]
        database = os.environ["POSTGRES_DB"]
    except KeyError as err:
        raise KeyError(
            f"Required Postgres env var {err!s} is not set."
        ) from err

    port = int(os.environ.get("POSTGRES_PORT", "5432"))
    sslmode = os.environ.get("POSTGRES_SSLMODE", "disable")

    user, password = read_pg_credentials(secrets_dir)

    url = URL.create(
        drivername="postgresql+psycopg",
        username=user,
        password=password,
        host=host,
        port=port,
        database=database,
        query={"sslmode": sslmode} if sslmode else {},
    )
    return create_engine(url)


def make_sessionmaker(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


def init_schema(engine: Engine) -> None:
    """Create all known tables. Alembic to be added later."""
    Base.metadata.create_all(engine)
