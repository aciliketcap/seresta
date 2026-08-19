"""The used car listing project's half of the composition root.

Between serespar's `ParserBuilder`, which knows how to assemble any parsing
application, and a site's own builder, which knows what carwow or Big Motoring
World is made of, sits what every parser in this project shares: one database,
one schema, one `source` table to seed, and the `parsing_session` row every run
records itself in.

A site's builder therefore names its classes and, at most, overrides the odd
hook -- see `CarWowUsedCarListingParserBuilder`.

The three levels mirror the config cascade exactly: serespar -> project ->
parser. That is not a coincidence; it is the same layering seen from the
assembly side.
"""

import logging

from serespar import ParserBuilder
from serespar.config import EffectiveConfig
from serespar.db.repos import SessionReportRepository
from sqlalchemy.orm import Session, sessionmaker

from .base_repos import BaseRawUsedCarListingSqlAlchemyRepository, seed_sources
from .config import UsedCarListingProjectConfig
from .db import build_engine, init_schema, make_sessionmaker

logger = logging.getLogger(__name__)


class UsedCarListingParserBuilder[ConfigT: EffectiveConfig](ParserBuilder[ConfigT]):
    """Builds a used car listing parser: whatever the site, this is the storage."""

    project_config_cls = UsedCarListingProjectConfig

    #: The site's repository class. It is handed the project's sessionmaker.
    repository_cls: type[BaseRawUsedCarListingSqlAlchemyRepository] | None = None

    #: Built once, on first use, and shared by the repository and the reporter.
    _sessionmaker: sessionmaker[Session] | None = None

    def build_repository(self, config: ConfigT) -> BaseRawUsedCarListingSqlAlchemyRepository:
        """The `DataSink`: this site's listings, into the project's schema."""
        if self.repository_cls is None:
            return super().build_repository(config)
        return self.repository_cls(self.sessionmaker(config))

    def build_session_reporter(self, config: ConfigT) -> SessionReportRepository:
        """Every run records itself in the `parsing_session` table.

        Unless one was handed to the builder -- a test reporting somewhere
        else, or nowhere.
        """
        if self._session_reporter is not None:
            return self._session_reporter
        return SessionReportRepository(self.sessionmaker(config))

    def sessionmaker(self, config: ConfigT) -> sessionmaker[Session]:
        """The project's database, opened once for this application.

        Schema creation and the `source` seed live here because they are
        start-up concerns of the whole application, not of any one of the
        pieces that use the connection.
        """
        if self._sessionmaker is None:
            engine = build_engine(config)
            init_schema(engine)
            self._sessionmaker = make_sessionmaker(engine)
            seed_sources(self._sessionmaker)
            logger.info("Database ready at %s/%s", config.db_host, config.db_name)
        return self._sessionmaker
