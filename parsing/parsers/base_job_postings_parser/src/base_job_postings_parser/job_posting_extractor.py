"""Base class which takes job cards from playwright and sends them to the attached repo for persistence."""
from playwright.sync_api import Locator, Page

from .base_repos import AbstractBaseRawJobPostingRepository

class JobPostingExtractionError(Exception):
    pass

class JobPostingExtractor:
    def __init__(self, repo: AbstractBaseRawJobPostingRepository) -> None:
        self._repo = repo

    def extract_and_persist(self, page: Page, job_card: Locator, parsing_session_id: int) -> None:
        """Abstract method, it should try to persist the job card in the repo.

        ``parsing_session_id`` is stored on the posting's ``last_found_in`` field and
        used to link the result to the current parsing session.
        """
        pass

