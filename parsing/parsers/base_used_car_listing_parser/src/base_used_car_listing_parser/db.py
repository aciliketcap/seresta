"""SQLAlchemy bootstrap helpers shared by all used car listing parsers.

This module owns the declarative ``Base`` so that all ORM classes across
``base_used_car_listing_parser`` and apps derived from it register with a single
``MetaData`` instance.

Connection info is split between:

- the `ProjectConfig` layer for non-secret configuration (host, port, db,
  sslmode), so those defaults live on the config model rather than here;
- two secrets for user and password, read from the Docker secrets mount and
  falling back to the environment.
"""

import os

from pydantic import ValidationError
from serespar.config import ConfigurationException, ProjectConfig, ProjectSettings
from sqlalchemy import URL, Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

SECRETS_DIR = "/run/secrets"

class Base(DeclarativeBase):
    """Declarative base for every ORM class in this project."""

def get_secret(secret_name) -> str:
    """Reads a Docker secret from the standard /run/secrets/ mount point or raises IOError."""
    # TODO: modify this to work with Vault secrets as well
    with open(f'{SECRETS_DIR}/{secret_name}', 'r') as secret_file:
            return secret_file.read().strip()

def read_pg_creds_from_files() -> tuple[str, str]:
    user = get_secret("db_user")
    password = get_secret("db_password")

    return user, password

def read_pg_creds_from_env() -> tuple[str, str]:
    try:
        user = os.environ["SERESPAR_DB_USER"]
        password = os.environ["SERESPAR_DB_PASSWORD"]
        return user, password
    except KeyError as err:
        raise ConfigurationException(
            f"Required Postgres env var {err!s} is not set."
        ) from err

def read_pg_credentials() -> tuple[str, str]:
    """Try to read from docker secrets dir. Otherwise read from env vars"""
    try:
        return read_pg_creds_from_files()
    except IOError:
        return read_pg_creds_from_env()

def build_engine(project: ProjectConfig) -> Engine:
    """Build a SQLAlchemy ``Engine`` for the project's database.

    Everything but the credentials comes from the `ProjectConfig` layer, so the
    port and sslmode defaults live on the model.
    """
    user, password = read_pg_credentials()

    url = URL.create(
        drivername="postgresql+psycopg",
        username=user,
        password=password,
        host=project.db_host,
        port=project.db_port,
        database=project.db_name,
        query={"sslmode": project.db_sslmode} if project.db_sslmode else {},
    )
    return create_engine(url)


def build_engine_from_env() -> Engine:
    """`build_engine` with the project layer read from the environment."""
    try:
        project = ProjectSettings()
    except ValidationError as err:
        raise ConfigurationException(
            f"The Postgres configuration is incomplete: {err}"
        ) from err

    return build_engine(project)


def make_sessionmaker(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)

def init_schema(engine: Engine) -> None:
    """Create all known tables. Alembic to be added later."""
    Base.metadata.create_all(engine)
