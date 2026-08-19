#!/usr/bin/env python3

import argparse
import logging
import os
from pathlib import Path

from serespar import SessionTracker

from base_used_car_listing_parser import (
    build_engine_from_env,
    init_schema,
    make_sessionmaker,
    seed_sources,
)

from .big_motoring_world_used_car_listing_parser import BigMotoringWorldParsingSession

from .big_motoring_world_repos import BigMotoringWorldRawUsedCarListingSqlAlchemyRepository
from .big_motoring_world_used_car_listing_extractor import BigMotoringWorldUsedCarListingExtractor

# TODO: use debug during dev and a sensible logging level in prod
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)

secrets_dir = Path(os.environ["SECRETS_DIR"])
MAX_DEPTH = int(os.environ.get("MAX_DEPTH", 5))

parser = argparse.ArgumentParser(description='Traverse search results at the given OriginUrl')
parser.add_argument('origin_url', help='OriginUrl of the search')
parser.add_argument('-a', '--auth-material-path',
    default=secrets_dir/"linkedin_cookies.json",
    help='Path of the AuthMaterial (cookies) file')
opts = parser.parse_args()

engine = build_engine_from_env()
init_schema(engine)
sm = make_sessionmaker(engine)
seed_sources(sm)

# The persistence layer this session drains into: the glossary's `DataSink`.
# TODO: heading into `ParsingSession` itself in the architecture refactor.
data_sink = BigMotoringWorldRawUsedCarListingSqlAlchemyRepository(sm)

with BigMotoringWorldParsingSession(opts.origin_url, sm, opts.auth_material_path) as session:
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
                with BigMotoringWorldUsedCarListingExtractor(
                    data_sink,
                    page,
                    car_card,
                    tracker
                    ) as xtor:
                    logger.info("Found another car listing!")
                    xtor.extract_and_persist()
            except Exception:
                session.num_failed_results += 1
            
