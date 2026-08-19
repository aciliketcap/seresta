"""The job postings project's declarative ``Base``, on serespar's bootstrap.

The engine, credentials and sessionmaker helpers live in
`serespar.db.postgres`; every project shares them. What stays here is the one
thing that must not be shared: the declarative ``Base``, so that all ORM
classes across ``base_job_postings_parser`` and apps derived from it
register with a single ``MetaData`` instance -- and *only* they do, since the
used car listing project names its tables the same.
"""

from sqlalchemy import Engine
from sqlalchemy.orm import DeclarativeBase

from serespar.db import postgres
from serespar.db.postgres import (
    build_engine_from_env,
    get_secret,
    make_sessionmaker,
    read_pg_credentials,
)

__all__ = [
    "Base",
    "build_engine_from_env",
    "get_secret",
    "init_schema",
    "make_sessionmaker",
    "read_pg_credentials",
]


class Base(DeclarativeBase):
    """Declarative base for every ORM class in this project."""


def init_schema(engine: Engine) -> None:
    """Create this project's tables. Alembic to be added later."""
    postgres.init_schema(engine, Base)
