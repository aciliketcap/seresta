"""Base parse session for job posting scrapers.

Subclasses serespar's ``ResultsParseSession`` and, on top of the browser
lifecycle, owns a ``parse_session`` row: it is created (with a start date) when
the context is entered and stamped with an end date when the context exits.
"""

import logging
from typing import Self

from sqlalchemy.orm import Session, sessionmaker
from serespar import ResultsParseSession

from .base_repos import ParseSessionRepository, Source

logger = logging.getLogger(__name__)


class BaseJobPostingsParseSession(ResultsParseSession):
    """A parse session that records itself in the ``parse_session`` table.

    Concrete scrapers subclass this, set the ``SOURCE`` class attribute, and
    implement the abstract ``paginations_in_search_results`` /
    ``results_in_pagination`` generators from ``ResultsParseSession``.
    """

    # Set by each concrete subclass, e.g. ``SOURCE = Source.LINKEDIN``.
    SOURCE: Source

    def __init__(
        self,
        target: str,
        sm: sessionmaker[Session],
        cookie_path: str | None = None,
    ) -> None:
        super().__init__(target, cookie_path)
        self._parse_session_repo = ParseSessionRepository(sm)
        self.parse_session_id: int | None = None

    def __enter__(self) -> Self:
        super().__enter__()
        self.parse_session_id = self._parse_session_repo.start(int(self.SOURCE))
        logger.info(
            "Started job posting parse session %s for source %s",
            self.parse_session_id,
            self.SOURCE.name,
        )
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        if self.parse_session_id is not None:
            self._parse_session_repo.end(self.parse_session_id)
            logger.info(
                "Ended job posting parse session %s for source %s",
                self.parse_session_id,
                self.SOURCE.name,
            )
        super().__exit__(exc_type, exc_value, traceback)
