"""A model of the info in the car cards. Called raw because the listing is not processed yet."""

import abc
import logging
from datetime import datetime
from enum import IntEnum

from pydantic import BaseModel, ConfigDict, Field
from pydantic_core import Url
from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    select,
)
from sqlalchemy.orm import Mapped, Session, mapped_column, sessionmaker

from .db import Base

logger = logging.getLogger(__name__)


class Source(IntEnum):
    """The websites we gather used car listings from.

    The integer values are the primary keys seeded into the ``source`` table and
    are used as the joined-table-inheritance polymorphic identity of each
    concrete listing ORM. They are fixed per app base / db schema.

    The value ``0`` is reserved as the polymorphic-identity sentinel for the
    base (non-subclassed) ``raw_used_car_listing`` rows — see
    ``BaseRawUsedCarListingORM.__mapper_args__`` — so concrete members must
    start at ``1`` and never use ``0``.
    """

    BIG_MOTORING_WORLD = 1
    CARWOW = 2


# Seed data for the `source` table: enum member -> (name, search_url, description).
# "Seed" = static reference data the app requires at runtime (FK targets for
# `parse_session.source` and polymorphic identities for the joined-table
# inheritance), not rows users ever create. Normally this would live in a data
# migration; we apply it at startup via `seed_sources()` because we don't have
# migrations set up yet. TODO: move into a data migration once migrations land.
# Note: a single website can be listed as several `source` rows with different
# search URLs (e.g. different saved searches/filters). Only `name` is unique, so
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


class SourceORM(Base):
    """A website we scrape used car listings from.

    The same physical website may appear as multiple rows here with different
    ``search_url`` values (different saved searches/filters); ``name`` is the
    unique key and corresponds to a member of the :class:`Source` enum.
    """

    __tablename__ = "source"

    # id is only used for joining; it is seeded from the Source enum.
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    search_url: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(String, nullable=True)


class ParseSessionORM(Base):
    """One scraping run ("search session") against a single source."""

    __tablename__ = "parse_session"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    start_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    source: Mapped[int] = mapped_column(
        ForeignKey("source.id"), nullable=False
    )


class SearchResultInParseSessionORM(Base):
    """Joining table: a search result that was found in a parse session."""

    __tablename__ = "search_result_in_parse_session"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    search_result_id: Mapped[int] = mapped_column(
        ForeignKey("raw_used_car_listing.id", ondelete="CASCADE"), nullable=False
    )
    parse_session_id: Mapped[int] = mapped_column(
        ForeignKey("parse_session.id"), nullable=False
    )


class BaseRawUsedCarListing(BaseModel):
    """A used car listing as it was initially extracted (therefore raw)"""
    model_config = ConfigDict(from_attributes=True)

    # Assigned by the database (autoincrement); unset until persisted.
    id: int | None = Field(default=None, description="Database primary key")
    # Typed as ``Source`` (an IntEnum), not ``int``, so pydantic rejects
    # values that don't correspond to a seeded source row at construction time.
    source: Source = Field(description="FK to the source table (see Source enum)")
    seres_id: str = Field(description="Search Result Id: the listing's own id within the source website")
    last_found_in: int | None = Field(
        default=None,
        description="FK to the parse session in which this listing was last found",
    )
    url: Url = Field(description="The URL of the used car listing")
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

class BaseRawUsedCarListingORM(Base):
    """SQLAlchemy ORM mapping for ``BaseRawUsedCarListing`` (joined-table inheritance root)."""

    __tablename__ = "raw_used_car_listing"

    # seres_id is unique within a source (the discriminator column), so the same
    # listing id appearing on two different sources doesn't collide.
    __table_args__ = (
        UniqueConstraint("source", "seres_id", name="uq_raw_used_car_listing_source_seres_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[int] = mapped_column(ForeignKey("source.id"), nullable=False)
    seres_id: Mapped[str] = mapped_column(String, nullable=False)
    last_found_in: Mapped[int | None] = mapped_column(
        ForeignKey("parse_session.id"), nullable=True
    )
    url: Mapped[str] = mapped_column(String, nullable=False)
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

    __mapper_args__ = {
        "polymorphic_on": "source",
        # Sentinel identity for plain (non-subclassed) BaseRawUsedCarListing rows.
        # Real sources (Source.CARWOW, ...) override this on the ORM subclass with
        # their seeded source id.
        "polymorphic_identity": 0,
    }

class AbstractBaseRawUsedCarListingRepository(abc.ABC):
    @abc.abstractmethod
    def add(self, used_car_listing: BaseRawUsedCarListing) -> None:
        pass

    @abc.abstractmethod
    def get(self, used_car_listing_id: int) -> BaseRawUsedCarListing | None:
        pass


# Setting it into stone that an sqlalchemy repo will exist eventually is for convenience. But it is also unnecessary rigidity, bringing in sqlalchemy dependency to all sub-projects.
class BaseRawUsedCarListingSqlAlchemyRepository(AbstractBaseRawUsedCarListingRepository):
    # Subclasses override these with their concrete ORM + Pydantic classes.
    ORM: type[BaseRawUsedCarListingORM] = BaseRawUsedCarListingORM
    PYDANTIC: type[BaseRawUsedCarListing] = BaseRawUsedCarListing

    def __init__(self, sm: sessionmaker[Session]) -> None:
        self._sm = sm

    def add(self, used_car_listing: BaseRawUsedCarListing) -> None:
        # One transaction for the dedup check + insert + join-row write, so
        # there's no TOCTOU window between "is this seres_id already there?"
        # and the insert.
        # A polymorphic query on the concrete ORM only matches rows of this
        # source, so checking seres_id here is effectively per-source.
        with self._sm.begin() as session:
            existing = session.scalar(
                select(self.ORM).where(self.ORM.seres_id == used_car_listing.seres_id)
            )
            if existing is not None:
                # TODO: when a listing already exists we should update its
                # last_found_in and link it to the current parse session. For now
                # we just log the situation and move on to the next result.
                logger.info(
                    "Used car listing seres_id=%s from source=%s already exists "
                    "(id=%s); skipping (dedup handling not implemented yet).",
                    used_car_listing.seres_id,
                    used_car_listing.source,
                    existing.id,
                )
                return

            # mode="json" so pydantic_core.Url becomes str for the String column.
            # id is unset (autoincrement), so exclude it from the insert.
            orm = self.ORM(**used_car_listing.model_dump(mode="json", exclude={"id"}))
            session.add(orm)
            session.flush()  # populate orm.id for the joining-table row
            if used_car_listing.last_found_in is not None:
                session.add(
                    SearchResultInParseSessionORM(
                        search_result_id=orm.id,
                        parse_session_id=used_car_listing.last_found_in,
                    )
                )

    def get(self, used_car_listing_id: int) -> BaseRawUsedCarListing | None:
        with self._sm() as session:
            # Polymorphism returns the concrete ORM subclass; model_validate
            # then yields the matching Pydantic subclass.
            row = session.get(self.ORM, used_car_listing_id)
            return self.PYDANTIC.model_validate(row) if row is not None else None  # type: ignore[return-value]


class ParseSessionRepository:
    """Creates and closes ``parse_session`` rows."""

    def __init__(self, sm: sessionmaker[Session]) -> None:
        self._sm = sm

    def start(self, source_id: int) -> int:
        """Open a parse session with a start date and return its new id."""
        with self._sm.begin() as session:
            parse_session = ParseSessionORM(start_date=datetime.now(), source=source_id)
            session.add(parse_session)
            session.flush()
            return parse_session.id

    def end(self, parse_session_id: int) -> None:
        """Stamp the end date on an open parse session."""
        with self._sm.begin() as session:
            parse_session = session.get(ParseSessionORM, parse_session_id)
            if parse_session is not None:
                parse_session.end_date = datetime.now()


def seed_sources(sm: sessionmaker[Session]) -> None:
    """Idempotently seed the ``source`` table from the :class:`Source` enum."""
    with sm.begin() as session:
        for source in Source:
            if session.get(SourceORM, int(source)) is not None:
                continue
            name, search_url, description = SOURCE_SEED[source]
            session.add(
                SourceORM(
                    id=int(source),
                    name=name,
                    search_url=search_url,
                    description=description,
                )
            )
