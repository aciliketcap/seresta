"""The SQLAlchemy repositories every project shares.

The `DataSink` half that has nothing domain-specific in it: writing a
`ParsedEntity` into its table with a dedup check, opening and closing the
`parsing_session` row, and seeding the `source` table. A project subclasses
`SqlAlchemyEntityRepository` and points it at its own ORM and pydantic
classes.

TODO: none of this is the glossary's session-bound `SessionRepository` yet --
each `add()` opens its own transaction, so there is no batch semantics and no
final flush, and driver errors leak out instead of surfacing as
`SessionRepositoryException`.
"""

import logging
from datetime import datetime
from enum import IntEnum
from typing import ClassVar

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from ..base_repos import AbstractBaseRepository, ParsedEntityT
from .orm import (
    AbstractParsedEntityInParsingSessionORM,
    AbstractParsedEntityORM,
    ParsingSessionORM,
    SourceORM,
)

logger = logging.getLogger(__name__)


class SqlAlchemyEntityRepository(AbstractBaseRepository[ParsedEntityT]):
    """Persists a `ParsedEntity` into its project's table.

    Subclasses set the three class attributes; the add/get logic is the same
    for every project, and joined-table inheritance takes care of the per-site
    subclasses.
    """

    # Subclasses override these with their concrete ORM + Pydantic classes.
    ORM: ClassVar[type[AbstractParsedEntityORM]]
    PYDANTIC: ClassVar[type[BaseModel]]
    JOIN_ORM: ClassVar[type[AbstractParsedEntityInParsingSessionORM]]

    def __init__(self, sm: sessionmaker[Session]) -> None:
        self._sm = sm

    def add(self, parsed_entity: ParsedEntityT) -> None:
        # One transaction for the dedup check + insert + join-row write, so
        # there's no TOCTOU window between "is this result_id already there?"
        # and the insert.
        # A polymorphic query on the concrete ORM only matches rows of this
        # source, so checking result_id here is effectively per-source.
        with self._sm.begin() as session:
            existing = session.scalar(
                select(self.ORM).where(self.ORM.result_id == parsed_entity.result_id)
            )
            if existing is not None:
                # TODO: when an entity already exists we should update its
                # last_found_in and link it to the current parsing session. For now
                # we just log the situation and move on to the next result.
                logger.info(
                    "Parsed entity result_id=%s from source=%s already exists "
                    "(id=%s); skipping (dedup handling not implemented yet).",
                    parsed_entity.result_id,
                    parsed_entity.source,
                    existing.id,
                )
                return

            # mode="json" so pydantic_core.Url becomes str for the String column.
            # id is unset (autoincrement), so exclude it from the insert.
            orm = self.ORM(**parsed_entity.model_dump(mode="json", exclude={"id"}))
            session.add(orm)
            session.flush()  # populate orm.id for the joining-table row
            if parsed_entity.last_found_in is not None:
                session.add(
                    self.JOIN_ORM(
                        parsed_entity_id=orm.id,
                        parsing_session_id=parsed_entity.last_found_in,
                    )
                )

    def get(self, entity_id: int) -> ParsedEntityT | None:
        with self._sm() as session:
            # Polymorphism returns the concrete ORM subclass; model_validate
            # then yields the matching Pydantic subclass.
            row = session.get(self.ORM, entity_id)
            return self.PYDANTIC.model_validate(row) if row is not None else None  # type: ignore[return-value]


class SessionReportRepository:
    """Creates and closes the ``parsing_session`` row of the current run.

    Its start and end dates are the beginnings of the session's `SessionReport`;
    see that entry in ``parsing/docs/glossary.md``. Not to be confused with the
    glossary's `SessionRepository`, which is where the extracted entities go.
    """

    def __init__(self, sm: sessionmaker[Session]) -> None:
        self._sm = sm

    def start(self, source_id: int) -> int:
        """Open a parsing session with a start date and return its new id."""
        with self._sm.begin() as session:
            parsing_session = ParsingSessionORM(start_date=datetime.now(), source=source_id)
            session.add(parsing_session)
            session.flush()
            return parsing_session.id

    def end(self, parsing_session_id: int) -> None:
        """Stamp the end date on an open parsing session."""
        with self._sm.begin() as session:
            parsing_session = session.get(ParsingSessionORM, parsing_session_id)
            if parsing_session is not None:
                parsing_session.end_date = datetime.now()


def seed_sources(
    sm: sessionmaker[Session],
    source_seed: dict[IntEnum, tuple[str, str, str]],
) -> None:
    """Idempotently seed the ``source`` table from a project's ``Source`` enum.

    ``source_seed`` maps each enum member to its ``(name, origin_url,
    description)``.
    """
    with sm.begin() as session:
        for source, (name, origin_url, description) in source_seed.items():
            if session.get(SourceORM, int(source)) is not None:
                continue
            session.add(
                SourceORM(
                    id=int(source),
                    name=name,
                    origin_url=origin_url,
                    description=description,
                )
            )
