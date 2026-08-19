#!/usr/bin/env python3
"""Entry point: build the carwow application and run the task.

Everything that decides *what* is being built is in `builder.py`; everything
that decides *how* it runs is in the config layers it resolves.
"""

import logging

from .builder import CarWowUsedCarListingParserBuilder

# TODO: use debug during dev and a sensible logging level in prod
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

report = CarWowUsedCarListingParserBuilder().build().run()

logger.info(
    "Parsing session %s finished: %s results in %s pagination batches, %s failed.",
    report.parsing_session_id,
    report.results,
    report.pagination_batches,
    report.failed_results,
)
