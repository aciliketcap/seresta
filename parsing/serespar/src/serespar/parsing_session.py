import logging
import os
from datetime import datetime
import json
from pathlib import Path
from abc import abstractmethod
from typing import Generator, Any, Self

from playwright.sync_api import Locator, sync_playwright, Browser, Page, ViewportSize


logger = logging.getLogger(__name__)

DEFAULT_VIEWPORT_WIDTH = 1600
DEFAULT_VIEWPORT_HEIGHT = 1000

# Set this to ask for a visible browser window. Task definitions own it:
# dev-task.sh exports it, and the test task leaves it to the caller
# (`SERESPAR_HEADED=1 podman compose up`).
HEADED_ENV_VAR = "SERESPAR_HEADED"
TRUTHY_ENV_VALUES = frozenset({"1", "true", "yes", "on"})


def headed_from_env() -> bool:
    """Whether the environment is asking for a visible browser window.

    Anything other than a truthy value -- unset, empty, "0" -- means headless,
    so a session works on a machine with no X display unless told otherwise.
    """
    return os.environ.get(HEADED_ENV_VAR, "").strip().lower() in TRUTHY_ENV_VALUES


class ParsingSession():
    """The core orchestrator: it manages the main execution loop of one parsing run.

    A parsing session consists of:
        1. Opening a page
        2. Applying the `OriginQuery`, which opens a list of paginated search results
            - Preferably the `OriginUrl` contains everything so results come up directly. But if doing some action like filling in an input box and clicking a button is necessary it can be done by subclassing this class and overloading the `process_origin_query` function
        3. Going through the results of the current `PaginationBatch`:
            - Generator gives control to caller so that they can do smt like:
                - Click certain elements of some results fitting a criteria
                - Extract key info from the search result
        4. When the end of the batch is reached click the `NextPaginationTrigger` for the next batch
            - This is also done by the caller. Ofc this can work with infinite scrolling as well.
        5. We quit when we have reached `MaxDepth` in pagination. TODO: However we should be able to understand when we reach the end of pagination and quit there. Or after parsing a max number of entities.
        6. TODO: We should generate a `SessionReport` somewhere.

    TODO: the `SessionTracker` (limits, errors, "should we stop?") and the
    `SessionReport` are not broken out yet; `num_failed_results` and the
    start/end times below are all we track for now.
    """
    _start_time: datetime | None
    _end_time: datetime | None
    _browser: Browser
    _page: Page # playwright page object
    _auth_material_path: Path | str | None
    _origin_url: str
    _headless: bool
    num_failed_results: int

    def __init__(
            self,
            origin_url: str,
            auth_material_path: str | None = None,
            headless: bool | None = None) -> None:
        """`origin_url` is the base web address where the session enters the
        target website.

        `auth_material_path` points at the `AuthMaterial` to enter the site
        with. TODO: only a cookie file is supported, i.e. this is hardwired to
        what a `CookiePassiveFlow` would do; the `AuthFlow` hierarchy does not
        exist yet.

        `headless=None` reads the mode from `SERESPAR_HEADED`, which is how
        task definitions drive it. Pass a bool only to pin the mode in code,
        regardless of the environment."""
        self._auth_material_path = auth_material_path
        self._origin_url = origin_url
        self._headless = not headed_from_env() if headless is None else headless
        # TODO: make these readable from a config
        # TODO: can we make this a prop which can be set in real time?
        self._view_port = ViewportSize(width=DEFAULT_VIEWPORT_WIDTH, height=DEFAULT_VIEWPORT_HEIGHT)

    def __enter__(self) -> Self:
        self._start_time = datetime.now()
        self.num_failed_results = 0
        
        # get context and manually enter / exit instead of using with statement
        self._pw_ctx = sync_playwright()
        pw = self._pw_ctx.__enter__()

        # TODO: viewport size etc. needs to be passed from a config to here
        logger.info(f"Launching chromium {'headless' if self._headless else 'headed'}")
        self._browser = pw.chromium.launch(headless=self._headless)
        context = self._browser.new_context(
            viewport=self._view_port
        )
        logger.debug(f"ctx is {context}")

        if self._auth_material_path:
            try:
                with Path(self._auth_material_path).open() as auth_material_file:
                    context.add_cookies(json.loads(auth_material_file.read()))
            except Exception as err:
                logger.exception("Unable to get the auth material (cookies)")
                # TODO: this should be a StaleAuthMaterialException once the
                # AuthFlow hierarchy exists.
                raise Exception from err

        self._page: Page = context.new_page()
        
        self.process_origin_query()

        return self # with pw, page, browser and whatever?


    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self._end_time = datetime.now()
        # prep a basic SessionReport somewhere

        self._browser.close()
        self._pw_ctx.__exit__()

    def process_origin_query(self) -> None:
        """The `OriginQueryProcess`: apply the `OriginQuery` to the target site.

        Open the `OriginUrl` and do whatever is necessary to get paginated search results on the browser.

        Ideally we shouldn't need to type in the search phrase or click anything including a search button. However in cases where this is not possible subclass should override this function to do whatever is necessary.

        TODO: this is a method on the session rather than an injectable
        `OriginQueryProcess` component taking an `OriginQuery`; breaking it out
        is follow-up work.
        """
        self._page.goto(self._origin_url, wait_until="load")
        logger.info(f"URL `{self._origin_url}` should be loaded now.")

    @abstractmethod
    def pagination_batches(self, max_depth: int) -> Generator[int, Any, None]:
        """Yields the `PaginationIndex` of each `PaginationBatch`.

        This method clicks the `NextPaginationTrigger` until `MaxDepth` is reached or the batches are exhausted.

        TODO: the stepping belongs in a `PaginationBatchStepper` of its own.
        """
        # iterate pages in old code
        pass

    @abstractmethod
    def results_in_pagination_batch(self) -> Generator[tuple[Page, Locator], Any, Any]:
        """Yields the page plus the `ResultLocator` of each result in the current `PaginationBatch`."""
        # iterate_job_cards in old code but yields page + current result locator
        # so that calling traversal loop can do whatever it wants with it
        pass
