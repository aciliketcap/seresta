import logging
from datetime import datetime
import json
from pathlib import Path
from abc import abstractmethod
from typing import Generator, Any, Self

from playwright.sync_api import Locator, sync_playwright, Browser, Page, ViewportSize


logger = logging.getLogger(__name__)

DEFAULT_VIEWPORT_WIDTH = 1600
DEFAULT_VIEWPORT_HEIGHT = 1000


class ResultsParseSession():
    """
    A results parsing session consists of:
        1. Opening a page
        2. Entering a search term which opens a list of paginated search results
            - Preferably the URL contains everything so results come up directly. But if doing some action like filling in an input box and clicking a button is necessary it can be done by subclassing this class and overloading the `initiate_search` function
        3. Going through the list:
            - Generator gives control to caller so that they can do smt like:
                - Click certain elements of some results fitting a criteria
                - Extract key info from the search result
        4. When the end of list is reached click the pagination button for next page
            - This is also done by the caller. Ofc this can work with infinite scrolling as well.
        5. We quit when we have reached a certain depth in pagination. TODO: However we should be able to understand when we reach the end of pagination and quit there. Or after parsing a max number of elts.
        6. TODO: We should generate a report somewhere.
    """
    _start_time: datetime | None
    _end_time: datetime | None
    _browser: Browser
    _page: Page # playwright page object
    _cookie_path: Path | str | None
    _initial_search_page_url: str
    num_failed_results: int

    def __init__(
            self,
            target: str,
            cookie_path: str | None = None) -> None:
        self._cookie_path = cookie_path
        self._initial_search_page_url = target
        # TODO: make these readable from a config
        # TODO: can we make this a prop which can be set in real time?
        self._view_port = ViewportSize(width=DEFAULT_VIEWPORT_WIDTH, height=DEFAULT_VIEWPORT_HEIGHT)

    def __enter__(self) -> Self:
        self._start_time = datetime.now()
        self.num_failed_results = 0
        
        # get context and manually enter / exit instead of using with statement
        self._pw_ctx = sync_playwright()
        pw = self._pw_ctx.__enter__()

        # TODO: headless, viewport size etc. needs to be passed from a config to here
        self._browser = pw.chromium.launch(headless=False)
        context = self._browser.new_context(
            viewport=self._view_port
        )
        logger.debug(f"ctx is {context}")

        if self._cookie_path:
            try:
                with Path(self._cookie_path).open() as cookie_file:
                    context.add_cookies(json.loads(cookie_file.read()))
            except Exception as err:
                logger.exception("Unable to get cookies")
                raise Exception from err

        self._page: Page = context.new_page()
        
        self.initiate_search()

        return self # with pw, page, browser and whatever?


    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self._end_time = datetime.now()
        # prep a basic report somewhere

        self._browser.close()
        self._pw_ctx.__exit__()

    def initiate_search(self) -> None:
        """
        Open the search or results URL and do whatever is necessary to get paginated search results on the browser
        
        Ideally we shouldn't need to type in the search phrase or click anything including a search button. However in cases where this is not possible subclass should override this function to do whatever is necessary.
        """
        self._page.goto(self._initial_search_page_url, wait_until="load")
        logger.info(f"URL `{self._initial_search_page_url}` should be loaded now.")

    @abstractmethod
    def paginations_in_search_results(self, max_pagination: int) -> Generator[int, Any, None]:
        """This method clicks the next page in search results pagination until max_pagination page is reached or result pages are exhausted"""
        # iterate pages in old code
        pass

    @abstractmethod
    def results_in_pagination(self) -> Generator[tuple[Page, Locator], Any, Any]:
        # iterate_job_cards in old code but yields page + current card
        # so that calling traversal loop can do whatever it wants with it
        pass
