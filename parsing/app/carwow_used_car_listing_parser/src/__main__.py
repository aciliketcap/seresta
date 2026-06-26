#!/usr/bin/env python3

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

from .carwow_used_car_listing_parser import CarWowParseSession

from .carwow_repos import CarWowRawUsedCarListingSqlAlchemyRepository
from .carwow_used_car_listing_extractor import CarWowUsedCarListingExtractor

# TODO: use debug during dev and a sensible logging level in prod
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)

secrets_dir = Path(os.environ["SECRETS_DIR"])
MAX_PAGI_DEPTH = int(os.environ.get("MAX_PAGI_DEPTH", 5))

parser = argparse.ArgumentParser(description='Traverse job search results in given URL')
parser.add_argument('url', help='URL of the job search')
parser.add_argument('-c', '--cookies-file-path',
    default=secrets_dir/"linkedin_cookies.json",
    help='Path of the auth cookies file')
opts = parser.parse_args()

engine = build_engine_from_env(secrets_dir)
init_schema(engine)
sm = make_sessionmaker(engine)
seed_sources(sm)

repo = CarWowRawUsedCarListingSqlAlchemyRepository(sm)
extractor = CarWowUsedCarListingExtractor(repo)

with CarWowParseSession(opts.url, sm, opts.cookies_file_path) as session:
    logger.debug("Inside the session ctx!")

    for cur_pagi_num in session.paginations_in_search_results(MAX_PAGI_DEPTH):
        logger.debug(f"Currently on page {cur_pagi_num} of search results.")
        for result_tuple in session.results_in_pagination():
            page, car_card = result_tuple
            try:
                extractor.extract_and_persist(page, car_card, session.parse_session_id)
                logger.info("Found another car listing!")
            except Exception as e:
                logger.exception(msg="Failed to extract info from card:", exc_info=e)
            
