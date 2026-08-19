"""Base parsing session for used car listing scrapers, from before DI.

Subclasses serespar's ``ParsingSession`` and, on top of the browser
lifecycle, owns a ``parsing_session`` row: it is created (with a start date) when
the context is entered and stamped with an end date when the context exits.

TODO: an assembled application gets that row from `ParserApp` instead, which
takes a `SessionReporter` the builder injects -- see
`UsedCarListingParserBuilder`. carwow no longer subclasses this; Big Motoring
World still does, and this class goes when that parser is rewritten.
"""

import logging
from typing import Self

from sqlalchemy.orm import Session, sessionmaker
from serespar import ParsingSession

from .base_repos import SessionReportRepository, Source

logger = logging.getLogger(__name__)


class BaseUsedCarListingParsingSession(ParsingSession):
    """A parsing session that records itself in the ``parsing_session`` table.

    Concrete scrapers subclass this, set the ``SOURCE`` class attribute, and
    implement the abstract ``pagination_batches`` /
    ``results_in_pagination_batch`` generators from ``ParsingSession``.
    """

    # Set by each concrete subclass, e.g. ``SOURCE = Source.CARWOW``.
    SOURCE: Source

    def __init__(
        self,
        origin_url: str,
        sm: sessionmaker[Session],
        auth_material_path: str | None = None,
    ) -> None:
        super().__init__(origin_url, auth_material_path)
        self._session_report_repo = SessionReportRepository(sm)

    def __enter__(self) -> Self:
        super().__enter__()
        self.parsing_session_id = self._session_report_repo.start(int(self.SOURCE))
        logger.info(
            "Started used car listing parsing session %s for source %s",
            self.parsing_session_id,
            self.SOURCE.name,
        )
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        if self.parsing_session_id is not None:
            self._session_report_repo.end(self.parsing_session_id)
            logger.info(
                "Ended used car listing parsing session %s for source %s",
                self.parsing_session_id,
                self.SOURCE.name,
            )
        super().__exit__(exc_type, exc_value, traceback)
