import abc
from typing import TypeVar

from pydantic import BaseModel, ConfigDict, Field
from pydantic_core import Url

from .exceptions import SeresparException

# Pydantic BaseModel variant type: the domain object a parser produces.
ParsedEntityT = TypeVar('ParsedEntityT', bound=BaseModel)


class SessionRepositoryException(SeresparException):
    """The repository could not store a `ParsedEntity`.

    TODO: raised once the session-bound `SessionRepository` exists; ORM and
    driver errors leak straight out to the orchestrator today.
    """

class ParsedEntity(BaseModel):
    """The pure domain object a parser produces, before any storage concern.

    The fields every project's entity has. A project subclasses it and adds its
    domain fields, and narrows `source` to its own `Source` enum so pydantic
    rejects values that do not correspond to a seeded source row::

        class BaseRawUsedCarListing(ParsedEntity):
            source: Source
            make: str
            ...

    `result_id` is the id the *target website* gave the result, which is a
    different thing from `id`, the repository's own primary key. See the "two
    ids" note in `parsing/docs/glossary.md`.
    """

    model_config = ConfigDict(from_attributes=True)

    # Assigned by the database (autoincrement); unset until persisted.
    id: int | None = Field(default=None, description="Database primary key")
    source: int = Field(description="FK to the source table (see the Source enum)")
    result_id: str = Field(description="The result's own id within the source website")
    last_found_in: int | None = Field(
        default=None,
        description="FK to the parsing session in which this result was last found",
    )
    url: Url = Field(description="The URL of the result")


class AbstractBaseRepository[ParsedEntityT](abc.ABC):
    """The repository a `ParsedEntity` is handed to for persistence.

    This is the concrete half of the glossary's `DataSink`, which is a
    conceptual term rather than a class: see `parsing/docs/glossary.md`.

    ``get`` takes ``entity_id``, the repository's own primary key, which is a
    different thing from a `ParsedEntity`'s ``result_id`` (the id the target
    website gave the result).
    """
    @abc.abstractmethod
    def add(self, parsed_entity: ParsedEntityT) -> None:
        pass

    @abc.abstractmethod
    # Create your own ABC if your id is not int
    def get(self, entity_id: int) -> ParsedEntityT | None:
        pass
