#!/usr/bin/env python3

from time import sleep
from serespar import ParseItemContext
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
# TODO: this is also a config param!
MAX_PAGI_DEPTH = int(os.environ.get("MAX_PAGI_DEPTH", 10))

# There are 12 non-ad listings per page
MAX_PAGI_DEPTH = 80

parser = argparse.ArgumentParser(description='Traverse job search results in given URL')
parser.add_argument('url', help='URL of the job search')
parser.add_argument('-c', '--cookies-file-path',
    default=secrets_dir/"carwow_cookies.json",
    help='Path of the auth cookies file')
opts = parser.parse_args()

engine = build_engine_from_env(secrets_dir)
init_schema(engine)
sm = make_sessionmaker(engine)
seed_sources(sm)

repo = CarWowRawUsedCarListingSqlAlchemyRepository(sm)

with CarWowParseSession(opts.url, sm, opts.cookies_file_path) as session:
    logger.debug("Inside the session ctx!")

    for cur_pagi_num in session.paginations_in_search_results(MAX_PAGI_DEPTH):
        logger.debug(f"Currently on page {cur_pagi_num} of search results.")
        cur_item_num = 0
        for result_tuple in session.results_in_pagination():
            cur_item_num += 1
            page, car_card = result_tuple
            ctx = ParseItemContext(
                parse_session_id=session.parse_session_id,
                cur_pagi_num=cur_pagi_num,
                cur_item_num=cur_item_num
            )
            try:
                with CarWowUsedCarListingExtractor(
                    repo,
                    page,
                    car_card,
                    ctx
                    ) as xtor:
                    logger.info("Found another car listing!")
                    xtor.extract_and_persist()
            except Exception:
                session.num_failed_results += 1
            
