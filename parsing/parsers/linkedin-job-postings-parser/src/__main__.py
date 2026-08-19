#!/usr/bin/env python3

import argparse
import logging
import os
from pathlib import Path

from base_job_postings_parser import (
    build_engine_from_env,
    init_schema,
    make_sessionmaker,
    seed_sources,
)

from .linkedin_jobs_parser import LinkedInJobsParsingSession
from .linkedin_repos import LinkedInRawJobPostingSqlAlchemyRepository
from .linkedin_job_extractor import LinkedInJobPostingExtractor

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
data_sink = LinkedInRawJobPostingSqlAlchemyRepository(sm)
extractor = LinkedInJobPostingExtractor(data_sink)

with LinkedInJobsParsingSession(opts.origin_url, sm, opts.auth_material_path) as session:
    logger.debug("Inside the session context manager!")

    for pagination_index in session.pagination_batches(MAX_DEPTH):
        logger.debug(f"Currently on pagination batch {pagination_index} of search results.")
        for result_tuple in session.results_in_pagination_batch():
            page, job_card = result_tuple
            extractor.extract_and_persist(page, job_card, session.parsing_session_id)
            logger.info("Found another job ad!")
            
