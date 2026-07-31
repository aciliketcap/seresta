"""SQLAlchemy bootstrap helpers shared by all job posting parsers.

This module owns the declarative ``Base`` so that all ORM classes across
``base_job_postings_parser`` and apps derived from it register with a single
``MetaData`` instance.

Connection info is split between:

- environment variables for non-secret configuration (host, port, db,
  sslmode);
- two secrets for user and password
"""

import json
import os
from pathlib import Path

from sqlalchemy import URL, Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

class Base(DeclarativeBase):
    """Declarative base for every ORM class in this project."""

def get_secret(secret_name) -> str:
    """Reads a Docker secret from the standard /run/secrets/ mount point or raises IOError."""
    # TODO: modify this to work with Vault secrets as well
    with open(f'/run/secrets/{secret_name}', 'r') as secret_file:
            return secret_file.read().strip()

def read_pg_creds_from_files() -> tuple[str, str]:
    user = get_secret("db_user")
    password = get_secret("db_password")

    return user, password

def read_pg_creds_from_env() -> tuple[str, str]:
    try:
        user = os.environ["POSTGRES_USER"]
        password = os.environ["POSTGRES_PASSWORD"]
        return user, password
    except KeyError as err:
        raise KeyError(
            f"Required Postgres env var {err!s} is not set."
        ) from err

def read_pg_credentials() -> tuple[str, str]:
    """Try to read from docker secrets dir. Otherwise read from env vars"""
    try:
        return read_pg_creds_from_files()        
    except IOError:
        return read_pg_creds_from_env()

def build_engine_from_env() -> Engine:
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

    user, password = read_pg_credentials()

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
