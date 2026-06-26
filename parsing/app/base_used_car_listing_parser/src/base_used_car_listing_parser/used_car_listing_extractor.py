"""Base class which takes used car listings from playwright and sends them to the attached repo for persistence."""
from playwright.sync_api import Locator, Page

from .base_repos import AbstractBaseRawUsedCarListingRepository

class UsedCarListingExtractionError(Exception):
    pass

class UsedCarListingExtractor:
    def __init__(self, repo: AbstractBaseRawUsedCarListingRepository) -> None:
        self._repo = repo

    def extract_and_persist(self, page: Page, item: Locator, parse_session_id: int) -> None:
        """Abstract method to extract a record from the search result item and persist it in the repo.

        ``parse_session_id`` is stored on the listing's ``last_found_in`` field and
        used to link the result to the current parse session.
        """
        pass

