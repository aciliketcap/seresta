#!/usr/bin/env python3

import argparse
import logging
import os
from pathlib import Path

from base_job_postings_parser import (
    build_engine_from_env,
    init_schema,
    make_sessionmaker,
)

from .linkedin_jobs_parser import LinkedInJobsParseSession
from .linkedin_repos import LinkedInRawJobPostingSqlAlchemyRepository
from .linkedin_job_extractor import LinkedInJobPostingExtractor

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

repo = LinkedInRawJobPostingSqlAlchemyRepository(sm)
extractor = LinkedInJobPostingExtractor(repo)

with LinkedInJobsParseSession(opts.url, opts.cookies_file_path) as session:
    logger.debug("Inside the session ctx!")

    for cur_pagi_num in session.paginations_in_search_results(MAX_PAGI_DEPTH):
        logger.debug(f"Currently on page {cur_pagi_num} of search results.")
        for result_tuple in session.results_in_pagination():
            page, job_card = result_tuple
            extractor.extract_and_persist(*result_tuple)
            logger.info("Found another job ad!")
            
