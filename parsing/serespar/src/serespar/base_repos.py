import abc
from typing import TypeVar

from pydantic import BaseModel

# Pydantic BaseModel variant type: the domain object a parser produces.
ParsedEntityT = TypeVar('ParsedEntityT', bound=BaseModel)

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
