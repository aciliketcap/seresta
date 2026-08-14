#!/usr/bin/env python3

from time import sleep
from serespar import SessionTracker
import argparse
import logging
import os
from pathlib import Path

from base_used_car_listing_parser import (
    build_engine_from_env,
    init_schema,
    make_sessionmaker,
    seed_sources,
)

from .carwow_used_car_listing_parser import AUTH_MATERIAL_FILE, CarWowParsingSession

from .carwow_repos import CarWowRawUsedCarListingSqlAlchemyRepository
from .carwow_used_car_listing_extractor import CarWowUsedCarListingExtractor

# TODO: use debug during dev and a sensible logging level in prod
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)

# TODO: write proper config access stub pls
origin_url = os.environ["ORIGIN_URL"]

# TODO: this should be in task config!
MAX_DEPTH = int(os.environ.get("MAX_DEPTH", 10))

# There are 12 non-ad listings per page
MAX_DEPTH = 80

engine = build_engine_from_env()
init_schema(engine)
sm = make_sessionmaker(engine)
seed_sources(sm)

# The persistence layer this session drains into: the glossary's `DataSink`.
# TODO: heading into `ParsingSession` itself in the architecture refactor.
data_sink = CarWowRawUsedCarListingSqlAlchemyRepository(sm)

with CarWowParsingSession(origin_url, sm, AUTH_MATERIAL_FILE) as session:
    logger.debug("Inside the session context manager!")

    for pagination_index in session.pagination_batches(MAX_DEPTH):
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
            
