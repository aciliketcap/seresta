"""A model of the info in the job cards. Called raw because the JD is not processed yet."""

import abc
import logging
from datetime import datetime
from enum import IntEnum

from pydantic import BaseModel, ConfigDict, Field
from pydantic_core import Url
from sqlalchemy import (
    Boolean,
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
    """The websites we gather job postings from.

    The integer values are the primary keys seeded into the ``source`` table and
    are used as the joined-table-inheritance polymorphic identity of each
    concrete posting ORM. They are fixed per app base / db schema.

    The value ``0`` is reserved as the polymorphic-identity sentinel for the
    base (non-subclassed) ``raw_job_posting`` rows — see
    ``BaseRawJobPostingORM.__mapper_args__`` — so concrete members must start
    at ``1`` and never use ``0``.
    """

    LINKEDIN = 1


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
    Source.LINKEDIN: (
        "linkedin",
        "https://www.linkedin.com/jobs",
        "LinkedIn job postings",
    ),
}


class SourceORM(Base):
    """A website we scrape job postings from.

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
        ForeignKey("raw_job_posting.id", ondelete="CASCADE"), nullable=False
    )
    parse_session_id: Mapped[int] = mapped_column(
        ForeignKey("parse_session.id"), nullable=False
    )


class BaseRawJobPosting(BaseModel):
    """A job posting on job search websiteas it was initially extracted (therefore raw)"""
    model_config = ConfigDict(from_attributes=True)

    # Assigned by the database (autoincrement); unset until persisted.
    id: int | None = Field(default=None, description="Database primary key")
    # Typed as ``Source`` (an IntEnum), not ``int``, so pydantic rejects
    # values that don't correspond to a seeded source row at construction time.
    source: Source = Field(description="FK to the source table (see Source enum)")
    seres_id: str = Field(description="Search Result Id: the posting's own id within the source website")
    last_found_in: int | None = Field(
        default=None,
        description="FK to the parse session in which this posting was last found",
    )
    url: Url = Field(description="The URL of the job posting")
    title: str = Field(description="The title of the job posting")
    jd_text: str = Field(description="The job description as text")
    jd_html: str = Field(description="The job description as HTML")
    processed: bool = Field(default=False, description="Whether the raw job posting was processed before")


class BaseRawJobPostingORM(Base):
    """SQLAlchemy ORM mapping for ``BaseRawJobPosting`` (joined-table inheritance root)."""

    __tablename__ = "raw_job_posting"

    # seres_id is unique within a source (the discriminator column), so the same
    # posting id appearing on two different sources doesn't collide.
    __table_args__ = (
        UniqueConstraint("source", "seres_id", name="uq_raw_job_posting_source_seres_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[int] = mapped_column(ForeignKey("source.id"), nullable=False)
    seres_id: Mapped[str] = mapped_column(String, nullable=False)
    last_found_in: Mapped[int | None] = mapped_column(
        ForeignKey("parse_session.id"), nullable=True
    )
    url: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    jd_text: Mapped[str] = mapped_column(String, nullable=False)
    jd_html: Mapped[str] = mapped_column(String, nullable=False)
    processed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __mapper_args__ = {
        "polymorphic_on": "source",
        # Sentinel identity for plain (non-subclassed) BaseRawJobPosting rows.
        # Real sources (Source.LINKEDIN, ...) override this on the ORM subclass
        # with their seeded source id.
        "polymorphic_identity": 0,
    }

class AbstractBaseRawJobPostingRepository(abc.ABC):
    @abc.abstractmethod
    def add(self, job_posting: BaseRawJobPosting) -> None:
        pass

    @abc.abstractmethod
    def get(self, job_posting_id: int) -> BaseRawJobPosting | None:
        pass

    @abc.abstractmethod
    def find_all_by_processed(self, processed: bool) -> list[BaseRawJobPosting]:
        pass

# Setting it into stone that an sqlalchemy repo will exist eventually is for convenience. But it is also unnecessary rigidity, bringing in sqlalchemy dependency to all sub-projects.
class BaseRawJobPostingSqlAlchemyRepository(AbstractBaseRawJobPostingRepository):
    # Subclasses override these with their concrete ORM + Pydantic classes.
    ORM: type[BaseRawJobPostingORM] = BaseRawJobPostingORM
    PYDANTIC: type[BaseRawJobPosting] = BaseRawJobPosting

    def __init__(self, sm: sessionmaker[Session]) -> None:
        self._sm = sm

    def add(self, job_posting: BaseRawJobPosting) -> None:
        # One transaction for the dedup check + insert + join-row write, so
        # there's no TOCTOU window between "is this seres_id already there?"
        # and the insert.
        # A polymorphic query on the concrete ORM only matches rows of this
        # source, so checking seres_id here is effectively per-source.
        with self._sm.begin() as session:
            existing = session.scalar(
                select(self.ORM).where(self.ORM.seres_id == job_posting.seres_id)
            )
            if existing is not None:
                # TODO: when a posting already exists we should update its
                # last_found_in and link it to the current parse session. For now
                # we just log the situation and move on to the next result.
                logger.info(
                    "Job posting seres_id=%s from source=%s already exists "
                    "(id=%s); skipping (dedup handling not implemented yet).",
                    job_posting.seres_id,
                    job_posting.source,
                    existing.id,
                )
                return

            # mode="json" so pydantic_core.Url becomes str for the String column.
            # id is unset (autoincrement), so exclude it from the insert.
            orm = self.ORM(**job_posting.model_dump(mode="json", exclude={"id"}))
            session.add(orm)
            session.flush()  # populate orm.id for the joining-table row
            if job_posting.last_found_in is not None:
                session.add(
                    SearchResultInParseSessionORM(
                        search_result_id=orm.id,
                        parse_session_id=job_posting.last_found_in,
                    )
                )

    def get(self, job_posting_id: int) -> BaseRawJobPosting | None:
        with self._sm() as session:
            # Polymorphism returns the concrete ORM subclass; model_validate
            # then yields the matching Pydantic subclass.
            row = session.get(self.ORM, job_posting_id)
            return self.PYDANTIC.model_validate(row) if row is not None else None  # type: ignore[return-value]

    def find_all_by_processed(self, processed: bool) -> list[BaseRawJobPosting]:
        with self._sm() as session:
            rows = session.scalars(
                select(self.ORM).where(self.ORM.processed == processed)
            ).all()
            return [self.PYDANTIC.model_validate(r) for r in rows]  # type: ignore[misc]


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
