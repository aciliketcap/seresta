"""The application: one parsing task, assembled and run.

`ParserApp` is what the composition root builds (see `builder.py`) and what
`__main__.py` runs. It holds the resolved configuration and one instance of
each port -- the session that drives the browser, the repository the results
go to, the factory that makes an extractor per result, and optionally the
reporter that records the run -- and it owns the loop over them.

That loop is the use case: walk the `PaginationBatch`es, walk the results in
each, extract each result and hand it over, count what failed. It used to be
copied into every parser's `__main__.py`, which is why every parser drifted
from every other one.

Nothing here knows about Playwright, SQLAlchemy or an environment variable.
"""

import logging
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Generator, Self

from .base_extractor import SessionTracker
from .config import ConfigurationException, EffectiveConfig
from .exceptions import SeresparException
from .parsing_session import ParsingSession
from .ports import EntityRepository, ExtractorFactory, SessionReporter

logger = logging.getLogger(__name__)


class AppNotOpenException(SeresparException):
    """The application was asked to parse before it had a browser open."""

# The `parsing_session_id` an app without a `SessionReporter` puts on its
# results: nothing recorded the run, so there is no session row to point at.
UNREPORTED_PARSING_SESSION_ID = 0


@dataclass(frozen=True)
class SessionReport:
    """What one run did.

    The object the glossary's `SessionReport` has been missing: the
    `parsing_session` row a `SessionReporter` writes holds the identity and the
    dates, and this holds the counts as well. Returned by `ParserApp.run()`.
    """

    parsing_session_id: int
    started_at: datetime
    ended_at: datetime
    pagination_batches: int
    results: int
    failed_results: int


class ParserApp:
    """One assembled parsing application, ready to run.

    Built by a `ParserBuilder`; never construct one in the middle of a parser,
    because then something other than the composition root is deciding what is
    wired to what.
    """

    def __init__(
        self,
        config: EffectiveConfig,
        session: ParsingSession,
        repository: EntityRepository[Any],
        extractor_factory: ExtractorFactory,
        session_reporter: SessionReporter | None = None,
        source_id: int = 0,
    ) -> None:
        self.config = config
        self.session = session
        self.repository = repository
        self.extractor_factory = extractor_factory
        self.session_reporter = session_reporter
        self.source_id = source_id

        self.parsing_session_id = UNREPORTED_PARSING_SESSION_ID
        self._started_at: datetime | None = None
        self._ended_at: datetime | None = None
        self._pagination_batches = 0
        self._results = 0

    # -- lifecycle ---------------------------------------------------------

    def __enter__(self) -> Self:
        """Open the browser and the `SessionReport` that goes with the run."""
        self._started_at = datetime.now()
        self.session.__enter__()
        if self.session_reporter is not None:
            self.parsing_session_id = self.session_reporter.start(self.source_id)
            logger.info("Started parsing session %s", self.parsing_session_id)
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        try:
            if self.session_reporter is not None:
                self.session_reporter.end(self.parsing_session_id)
                logger.info("Ended parsing session %s", self.parsing_session_id)
        finally:
            self._ended_at = datetime.now()
            self.session.__exit__(exc_type, exc_value, traceback)

    # -- the use case ------------------------------------------------------

    def run(self) -> SessionReport:
        """Run the task from end to end and report on it."""
        with self:
            deque(self.run_pagination_batches(), maxlen=0)
        return self.report()

    def run_pagination_batches(self) -> Generator[int, Any, None]:
        """Run the task, yielding each `PaginationIndex` once its batch is done.

        The session has to be open already -- `run()` is the whole thing, this
        is for a caller that wants to do something between batches. Both walk
        the same loop, so a test that steps through it exercises what
        production runs.
        """
        if self._started_at is None:
            raise AppNotOpenException(
                "There is no browser open to parse with. Call `run()`, or "
                "enter the app first: `with app: ...`."
            )

        max_depth = self._max_depth()
        for pagination_index in self.session.pagination_batches(max_depth):
            logger.debug("On pagination batch %s of the search results.", pagination_index)
            self._run_pagination_batch(pagination_index)
            self._pagination_batches += 1
            yield pagination_index

    def _run_pagination_batch(self, pagination_index: int) -> None:
        for result_index, (page, result_locator) in enumerate(
            self.session.results_in_pagination_batch(), start=1
        ):
            self._results += 1
            tracker = SessionTracker(
                parsing_session_id=self.parsing_session_id,
                pagination_index=pagination_index,
                result_index=result_index,
            )
            try:
                with self.extractor_factory(page, result_locator, tracker) as extractor:
                    extractor.extract_and_persist()
            except Exception:
                # The extractor has already logged what went wrong and dropped
                # the result; the run carries on with the next one.
                self.session.num_failed_results += 1

    def report(self) -> SessionReport:
        """The `SessionReport` for the run so far."""
        started_at = self._started_at or datetime.now()
        return SessionReport(
            parsing_session_id=self.parsing_session_id,
            started_at=started_at,
            ended_at=self._ended_at or datetime.now(),
            pagination_batches=self._pagination_batches,
            results=self._results,
            failed_results=self.session.num_failed_results,
        )

    def _max_depth(self) -> int:
        """`MaxDepth` off the resolved config.

        Resolution fills it in from the project's `default_max_depth` when the
        task does not say, so `None` here means the config never went through
        the cascade.
        """
        if self.config.max_depth is None:
            raise ConfigurationException(
                "The resolved config has no `max_depth`, so the run has no "
                "idea when to stop paginating. Build the config through "
                "`ConfigCascade.resolve()`, which fills it in."
            )
        return self.config.max_depth
