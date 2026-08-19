"""The ports: what the application needs from the outside world.

Hexagonal architecture calls these the *driven* (secondary) ports -- the
interfaces the application drives, each implemented by an adapter that knows
about Playwright, SQLAlchemy or a test double. Nothing here imports an adapter,
and nothing here knows how any of it is done.

They are `typing.Protocol`s rather than base classes on purpose: an adapter
satisfies a port by having the right methods, so a repository written before
these ports existed, or a fake defined inside a test module, is a valid adapter
without inheriting anything. `AbstractBaseRepository` in `base_repos.py` stays
an ABC because it also hands its subclasses shared documentation and typing;
it satisfies `EntityRepository` structurally.

The *driving* (primary) side is the other end: `__main__.py` and the test suite
drive `ParserApp` (see `app.py`), which is the application itself.
"""

from typing import Any, Protocol, Self, runtime_checkable

from playwright.sync_api import Locator, Page

from .base_extractor import SessionTracker


@runtime_checkable
class EntityRepository[ParsedEntityT](Protocol):
    """Where a `ParsedEntity` goes: the concrete half of the `DataSink`.

    `AbstractBaseRepository` and the SQLAlchemy repositories implement it, and
    so does an in-memory fake that keeps everything in a list.
    """

    def add(self, parsed_entity: ParsedEntityT) -> None: ...

    def get(self, entity_id: int) -> ParsedEntityT | None: ...


@runtime_checkable
class SessionReporter(Protocol):
    """Records that a `ParsingSession` ran: the `SessionReport`'s storage.

    `SessionReportRepository` in `serespar/db/repos.py` is the SQLAlchemy
    adapter; an app that reports nowhere simply has none.
    """

    def start(self, source_id: int) -> int:
        """Open a session and return the id the results should point at."""
        ...

    def end(self, parsing_session_id: int) -> None:
        """Close the session opened under this id."""
        ...


class OriginQueryProcess(Protocol):
    """Applies the `OriginQuery` to the target site.

    The strategy the session runs when it opens: navigate to the `OriginUrl`
    and, if the site cannot express the query in a URL, fill in whatever forms
    it takes until the paginated search results are on screen.

    `NavigateToOriginUrl` in `origin_query.py` is the default;
    `CarWowFilterFormsQueryProcess` is the hand-filling one.
    """

    def open_results(self, page: Page) -> None: ...


class ResultExtractor(Protocol):
    """One result's worth of extraction, as a context manager.

    `BaseExtractor` and its subclasses are the implementation: entering stages
    a `ParsedEntity`, `extract_and_persist` fills it in, and leaving either
    hands it to the repository or discards it.
    """

    def __enter__(self) -> Self: ...

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> bool: ...

    def extract_and_persist(self) -> None: ...


class ExtractorFactory(Protocol):
    """Builds the `ResultExtractor` for one result.

    The application makes one per result, because an extractor is bound to the
    result it extracts. What it is bound to besides -- the repository, the base
    URL, whatever else a parser needs -- is closed over when the factory is
    built, which is the composition root's job.
    """

    def __call__(
        self, page: Page, result_locator: Locator, tracker: SessionTracker
    ) -> ResultExtractor: ...
