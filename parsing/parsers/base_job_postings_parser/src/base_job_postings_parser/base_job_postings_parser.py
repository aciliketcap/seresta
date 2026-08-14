"""Base parsing session for job posting scrapers.

Subclasses serespar's ``ParsingSession`` and, on top of the browser
lifecycle, owns a ``parsing_session`` row: it is created (with a start date) when
the context is entered and stamped with an end date when the context exits.
"""

import logging
from typing import Self

from sqlalchemy.orm import Session, sessionmaker
from serespar import ParsingSession

from .base_repos import SessionReportRepository, Source

logger = logging.getLogger(__name__)


class BaseJobPostingsParsingSession(ParsingSession):
    """A parsing session that records itself in the ``parsing_session`` table.

    Concrete scrapers subclass this, set the ``SOURCE`` class attribute, and
    implement the abstract ``pagination_batches`` /
    ``results_in_pagination_batch`` generators from ``ParsingSession``.
    """

    # Set by each concrete subclass, e.g. ``SOURCE = Source.LINKEDIN``.
    SOURCE: Source

    def __init__(
        self,
        origin_url: str,
        sm: sessionmaker[Session],
        auth_material_path: str | None = None,
    ) -> None:
        super().__init__(origin_url, auth_material_path)
        self._session_report_repo = SessionReportRepository(sm)
        self.parsing_session_id: int | None = None

    def __enter__(self) -> Self:
        super().__enter__()
        self.parsing_session_id = self._session_report_repo.start(int(self.SOURCE))
        logger.info(
            "Started job posting parsing session %s for source %s",
            self.parsing_session_id,
            self.SOURCE.name,
        )
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        if self.parsing_session_id is not None:
            self._session_report_repo.end(self.parsing_session_id)
            logger.info(
                "Ended job posting parsing session %s for source %s",
                self.parsing_session_id,
                self.SOURCE.name,
            )
        super().__exit__(exc_type, exc_value, traceback)
