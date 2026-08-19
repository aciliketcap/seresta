"""The declarative `Base` and the ORM classes every project shares.

`Base` lives here so that a project does not have to invent one: all ORM
classes across serespar and the `base_<project>_parser` packages register with
a single `MetaData`. Each project has its own database, so the table names do
not have to be unique across projects.

Two of the tables are the same everywhere and are therefore concrete here:
`source` and `parsing_session`. The two that carry domain fields --
the `EntityOrmRecord` itself and the joining table that points at it -- are
abstract, and a project subclasses them to add its own columns:

    class BaseRawUsedCarListingORM(AbstractParsedEntityORM):
        __tablename__ = "raw_used_car_listing"
        make: Mapped[str] = mapped_column(String, nullable=False)
        ...

See `parsing/docs/glossary.md` sections 5 and 8.
"""

from datetime import datetime
from typing import ClassVar

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column

# The polymorphic identity of a row that belongs to no concrete source, i.e. a
# plain `AbstractParsedEntityORM` subclass row. Concrete per-site subclasses
# override it with their seeded source id, so a project's `Source` enum must
# start at 1.
BASE_POLYMORPHIC_IDENTITY = 0


class Base(DeclarativeBase):
    """Declarative base for every ORM class in a project."""


class SourceORM(Base):
    """A website results are gathered from.

    The same physical website may appear as multiple rows here with different
    ``origin_url`` values (different saved searches/filters); ``name`` is the
    unique key and corresponds to a member of the project's ``Source`` enum.
    """

    __tablename__ = "source"

    # id is only used for joining; it is seeded from the Source enum.
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    origin_url: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(String, nullable=True)


class ParsingSessionORM(Base):
    """One `ParsingSession` run against a single source.

    The row is the identity of the session, and its start/end dates are the
    beginnings of the session's `SessionReport`. See the `SessionReport` entry
    in ``parsing/docs/glossary.md``.
    """

    __tablename__ = "parsing_session"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    start_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    @declared_attr
    def source(cls) -> Mapped[int]:
        return mapped_column(ForeignKey("source.id"), nullable=False)


def _has_mapped_parent(cls: type) -> bool:
    """Whether a class inherits from an already-mapped (non-abstract) class.

    True for the joined-table subclass a per-site parser declares, false for
    the root a project declares straight on `AbstractParsedEntityORM`.
    """
    return any(
        getattr(base, "__tablename__", None) is not None
        and not base.__dict__.get("__abstract__", False)
        for base in cls.__mro__[1:]
    )


class AbstractParsedEntityORM(Base):
    """The `EntityOrmRecord` root: the columns every parsed entity has.

    A project subclasses it, sets ``__tablename__`` and adds its domain
    columns; per-site parsers then subclass *that* with joined-table
    inheritance and their own ``polymorphic_identity``.
    """

    __abstract__ = True

    # Negative sort orders keep the shared columns ahead of the domain columns
    # a project adds, which is the order these tables already have.
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, sort_order=-50)
    result_id: Mapped[str] = mapped_column(String, nullable=False, sort_order=-48)
    url: Mapped[str] = mapped_column(String, nullable=False, sort_order=-46)

    @declared_attr
    def source(cls) -> Mapped[int]:
        return mapped_column(ForeignKey("source.id"), nullable=False, sort_order=-49)

    @declared_attr
    def last_found_in(cls) -> Mapped[int | None]:
        return mapped_column(ForeignKey("parsing_session.id"), nullable=True, sort_order=-47)

    @declared_attr.directive
    def __table_args__(cls) -> tuple:
        # result_id is unique within a source (the discriminator column), so the
        # same result id appearing on two different sources doesn't collide.
        # Only the root of the hierarchy carries it: a joined-table subclass
        # has neither of those columns in its own table.
        if _has_mapped_parent(cls):
            return ()
        return (
            UniqueConstraint(
                "source", "result_id", name=f"uq_{cls.__tablename__}_source_result_id"
            ),
        )

    @declared_attr.directive
    def __mapper_args__(cls) -> dict:
        return {
            "polymorphic_on": "source",
            "polymorphic_identity": BASE_POLYMORPHIC_IDENTITY,
        }


class AbstractParsedEntityInParsingSessionORM(Base):
    """Joining table: a parsed entity that was found in a parsing session.

    A project subclasses it, sets ``__tablename__`` and points
    ``PARSED_ENTITY_TABLE`` at its own entity table, which is the only part
    that differs between projects.
    """

    __abstract__ = True

    PARSED_ENTITY_TABLE: ClassVar[str]

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    @declared_attr
    def parsed_entity_id(cls) -> Mapped[int]:
        return mapped_column(
            ForeignKey(f"{cls.PARSED_ENTITY_TABLE}.id", ondelete="CASCADE"),
            nullable=False,
        )

    @declared_attr
    def parsing_session_id(cls) -> Mapped[int]:
        return mapped_column(ForeignKey("parsing_session.id"), nullable=False)
