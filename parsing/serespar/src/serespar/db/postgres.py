"""SQLAlchemy bootstrap helpers for parsers that persist into Postgres.

Every project has the same job to do here -- build an `Engine`, make a
`sessionmaker`, create the tables -- so it lives in serespar rather than being
copied into each `base_<project>_parser`.

Connection info is split between:

- the `ProjectConfig` layer for non-secret configuration (host, port, db,
  sslmode);
- two secrets for user and password, read from the Docker secrets mount and
  falling back to the environment.

The declarative `Base` these tables hang off is `serespar.db.orm.Base`, which
`init_schema` creates by default. A project that keeps a `Base` of its own --
`base_job_postings_parser` still does -- passes it explicitly.

The non-secret half is the `ProjectConfig` layer: `build_engine` takes one, so
the port and the sslmode default where every other default lives -- on the
config model -- rather than as literals here. `build_engine_from_env` reads
that layer from the environment (`SERESPAR_DB_*`).
"""

import os

from pydantic import ValidationError
from sqlalchemy import URL, Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from ..config import ConfigurationException, ProjectConfig, ProjectSettings
from .orm import Base

SECRETS_DIR = "/run/secrets"


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
    """Build a SQLAlchemy ``Engine`` for a project's database.

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
    """`build_engine` with the project layer read from the environment.

    Required env vars: ``SERESPAR_DB_HOST``, ``SERESPAR_DB_NAME`` -- unless the
    project's own `ProjectConfig` subclass defaults them.
    Optional env vars: ``SERESPAR_DB_PORT``, ``SERESPAR_DB_SSLMODE`` -- their
    defaults are `ProjectConfig`'s.
    """
    try:
        project = ProjectSettings()
    except ValidationError as err:
        raise ConfigurationException(
            f"The Postgres configuration is incomplete: {err}"
        ) from err

    return build_engine(project)


def make_sessionmaker(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)

def init_schema(engine: Engine, base: type[DeclarativeBase] = Base) -> None:
    """Create all tables registered on ``base``. Alembic to be added later."""
    base.metadata.create_all(engine)
