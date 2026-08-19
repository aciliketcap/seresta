"""A model of the info in the car cards. Called raw because the listing is not processed yet.

Only what is specific to used car listings lives here: the `Source` enum and
its seed data, the domain fields of a listing, and the repository bound to
them. The `source` and `parsing_session` tables, the shared columns of an
`EntityOrmRecord`, the joining table and the add/get logic all come from
serespar -- see `serespar/db/orm.py` and `serespar/db/repos.py`.
"""
import abc
import logging
from enum import IntEnum

from pydantic import Field
from serespar.base_repos import AbstractBaseRepository, ParsedEntity
from serespar.db.orm import (
    AbstractParsedEntityInParsingSessionORM,
    AbstractParsedEntityORM,
    ParsingSessionORM,
    SourceORM,
)
from serespar.db.repos import SessionReportRepository, SqlAlchemyEntityRepository
from serespar.db import repos as serespar_repos
from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, Session, mapped_column, sessionmaker

logger = logging.getLogger(__name__)

__all__ = [
    "AbstractBaseRawUsedCarListingRepository",
    "BaseRawUsedCarListing",
    "BaseRawUsedCarListingORM",
    "BaseRawUsedCarListingSqlAlchemyRepository",
    "ParsedEntityInParsingSessionORM",
    "ParsingSessionORM",
    "SessionReportRepository",
    "Source",
    "SourceORM",
    "seed_sources",
]


class Source(IntEnum):
    """The websites we gather used car listings from.

    The integer values are the primary keys seeded into the ``source`` table and
    are used as the joined-table-inheritance polymorphic identity of each
    concrete listing ORM. They are fixed per app base / db schema.

    The value ``0`` is reserved as the polymorphic-identity sentinel for the
    base (non-subclassed) ``raw_used_car_listing`` rows -- see
    ``serespar.db.orm.BASE_POLYMORPHIC_IDENTITY`` -- so concrete members must
    start at ``1`` and never use ``0``.
    """

    BIG_MOTORING_WORLD = 1
    CARWOW = 2


# Seed data for the `source` table: enum member -> (name, origin_url, description).
# "Seed" = static reference data the app requires at runtime (FK targets for
# `parsing_session.source` and polymorphic identities for the joined-table
# inheritance), not rows users ever create. Normally this would live in a data
# migration; we apply it at startup via `seed_sources()` because we don't have
# migrations set up yet. TODO: move into a data migration once migrations land.
# Note: a single website can be listed as several `source` rows with different
# origin URLs (e.g. different saved searches/filters). Only `name` is unique, so
# such variants must each get their own distinct enum member + name.
SOURCE_SEED: dict[Source, tuple[str, str, str]] = {
    Source.BIG_MOTORING_WORLD: (
        "big_motoring_world",
        "https://www.bigmotoringworld.co.uk/used-cars",
        "Big Motoring World used car listings",
    ),
    Source.CARWOW: (
        "carwow",
        "https://www.carwow.co.uk/used-cars",
        "Carwow used car listings",
    ),
}


class ParsedEntityInParsingSessionORM(AbstractParsedEntityInParsingSessionORM):
    """Joining table: a listing that was found in a parsing session."""

    __tablename__ = "parsed_entity_in_parsing_session"

    PARSED_ENTITY_TABLE = "raw_used_car_listing"


class BaseRawUsedCarListing(ParsedEntity):
    """A used car listing as it was initially extracted (therefore raw)"""

    # Typed as ``Source`` (an IntEnum), not ``int``, so pydantic rejects
    # values that don't correspond to a seeded source row at construction time.
    source: Source = Field(description="FK to the source table (see Source enum)")
    make: str = Field(description="The make of the used car")
    model: str = Field(description="The model of the used car")
    trim: str = Field(description="The trim of the used car")
    year: int = Field(description="The year of the used car")
    price: int = Field(description="The price of the used car")
    mileage: int = Field(description="The mileage of the used car")
    fuel_type: str = Field(description="The fuel type of the used car (petrol, diesel, hybrid, electric)")
    transmission: str = Field(description="The transmission of the used car (manual, automatic, CVT, etc.)")
    engine_size: int|None = Field(description="The engine size of the used car (petrol, diesel, hybrid)")
    range: int|None = Field(description="The range of the used car (electric)")
    location: str|None = Field(description="The location of the used car")


class BaseRawUsedCarListingORM(AbstractParsedEntityORM):
    """SQLAlchemy ORM mapping for ``BaseRawUsedCarListing`` (joined-table inheritance root)."""

    __tablename__ = "raw_used_car_listing"

    make: Mapped[str] = mapped_column(String, nullable=False)
    model: Mapped[str] = mapped_column(String, nullable=False)
    trim: Mapped[str] = mapped_column(String, nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[int] = mapped_column(Integer, nullable=False)
    mileage: Mapped[int] = mapped_column(Integer, nullable=False)
    fuel_type: Mapped[str] = mapped_column(String, nullable=False)
    transmission: Mapped[str] = mapped_column(String, nullable=False)
    engine_size: Mapped[int|None] = mapped_column(Integer, nullable=True)
    range: Mapped[int|None] = mapped_column(Integer, nullable=True)
    location: Mapped[str|None] = mapped_column(String, nullable=True)


class AbstractBaseRawUsedCarListingRepository(
    AbstractBaseRepository[BaseRawUsedCarListing]):
    @abc.abstractmethod
    def add(self, parsed_entity: BaseRawUsedCarListing) -> None:
        pass

    @abc.abstractmethod
    def get(self, entity_id: int) -> BaseRawUsedCarListing | None:
        pass


# Setting it into stone that an sqlalchemy repo will exist eventually is for convenience. But it is also unnecessary rigidity, bringing in sqlalchemy dependency to all sub-projects.
class BaseRawUsedCarListingSqlAlchemyRepository(SqlAlchemyEntityRepository[BaseRawUsedCarListing]):
    # Subclasses override the first two with their concrete ORM + Pydantic classes.
    ORM = BaseRawUsedCarListingORM
    PYDANTIC = BaseRawUsedCarListing
    JOIN_ORM = ParsedEntityInParsingSessionORM


def seed_sources(sm: sessionmaker[Session]) -> None:
    """Idempotently seed the ``source`` table from the :class:`Source` enum."""
    serespar_repos.seed_sources(sm, SOURCE_SEED)
