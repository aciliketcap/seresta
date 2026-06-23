"""Base class which takes used car listings from playwright and sends them to the attached repo for persistence."""
from playwright.sync_api import Locator, Page

from .base_repos import AbstractBaseRawUsedCarListingRepository

class UsedCarListingExtractionError(Exception):
    pass

class UsedCarListingExtractor:
    def __init__(self, repo: AbstractBaseRawUsedCarListingRepository) -> None:
        self._repo = repo

    def extract_and_persist(self, page: Page, item: Locator) -> None:
        """Abstract method to extract a record from the search result item and  persist it in the repo"""
        pass

