"""carwow's composition root.

Everything that makes this application carwow rather than any other used car
listing parser is declared here: its config layers, the session that walks its
results, the extractor that reads one, the repository its listings end up in,
and the strategy that types its search into the site's filters.

The storage half -- the engine, the schema, the `source` seed, the
`parsing_session` row -- comes from `UsedCarListingParserBuilder`, because it
is the same for every parser in this project. The assembling itself comes from
`serespar.ParserBuilder`.
"""

from base_used_car_listing_parser import UsedCarListingParserBuilder
from base_used_car_listing_parser.base_repos import Source

from .carwow_origin_query import CarWowFilterFormsQueryProcess
from .carwow_repos import CarWowRawUsedCarListingSqlAlchemyRepository
from .carwow_used_car_listing_extractor import CarWowUsedCarListingExtractor
from .carwow_used_car_listing_parser import CarWowParsingSession
from .config import CarWowConfig, CarWowParserConfig, CarWowTaskConfig


class CarWowUsedCarListingParserBuilder(UsedCarListingParserBuilder[CarWowConfig]):
    """Builds the carwow parsing application."""

    # The cascade: serespar's core layer, the used car listing project's, and
    # carwow's own parser and task layers, resolved into `CarWowConfig`.
    config_cls = CarWowConfig
    parser_config_cls = CarWowParserConfig
    task_config_cls = CarWowTaskConfig

    session_cls = CarWowParsingSession
    extractor_cls = CarWowUsedCarListingExtractor
    repository_cls = CarWowRawUsedCarListingSqlAlchemyRepository

    #: The seeded `source` row every listing and every session points at.
    source_id = int(Source.CARWOW)

    def build_origin_query_process(
        self, config: CarWowConfig
    ) -> CarWowFilterFormsQueryProcess:
        """carwow's filters are widgets, not URL parameters."""
        return CarWowFilterFormsQueryProcess(
            origin_url=config.base_origin_url,
            origin_query=config.origin_query,
            settle_seconds=config.form_settle_seconds,
        )
