#!/usr/bin/env python3

from serespar import SessionTracker
import logging

from base_used_car_listing_parser import (
    build_engine,
    init_schema,
    make_sessionmaker,
    seed_sources,
)

from .config import carwow_config
from .carwow_used_car_listing_parser import CarWowParsingSession

from .carwow_repos import CarWowRawUsedCarListingSqlAlchemyRepository
from .carwow_used_car_listing_extractor import CarWowUsedCarListingExtractor

# TODO: use debug during dev and a sensible logging level in prod
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)

# The whole cascade, resolved once.
# TODO: built and injected here once app initialisation uses DI; for now the
# session and the extractor reach for `carwow_config()` themselves.
config = carwow_config()

# The resolved config *is* the project layer, so the engine comes off it
# instead of the environment being read a second time.
engine = build_engine(config)
init_schema(engine)
sm = make_sessionmaker(engine)
seed_sources(sm)

# The persistence layer this session drains into: the glossary's `DataSink`.
# TODO: heading into `ParsingSession` itself in the architecture refactor.
data_sink = CarWowRawUsedCarListingSqlAlchemyRepository(sm)

with CarWowParsingSession(
        config.base_origin_url, sm, config.auth_material_path) as session:
    logger.debug("Inside the session context manager!")

    for pagination_index in session.pagination_batches(config.max_depth):
        logger.debug(f"Currently on pagination batch {pagination_index} of search results.")
        result_index = 0
        for result_tuple in session.results_in_pagination_batch():
            result_index += 1
            page, car_card = result_tuple
            tracker = SessionTracker(
                parsing_session_id=session.parsing_session_id,
                pagination_index=pagination_index,
                result_index=result_index
            )
            try:
                with CarWowUsedCarListingExtractor(
                    data_sink,
                    page,
                    car_card,
                    tracker
                    ) as xtor:
                    logger.info("Found another car listing!")
                    xtor.extract_and_persist()
            except Exception:
                session.num_failed_results += 1
            
