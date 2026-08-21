import logging
from datetime import datetime
import json
from pathlib import Path
from abc import abstractmethod
from typing import Generator, Any, Self

from playwright.sync_api import Locator, sync_playwright, Browser, Page, ViewportSize

from .config import CoreConfig, CoreSettings
from .exceptions import SeresparException
from .origin_query import NavigateToOriginUrl
from .ports import OriginQueryProcess


logger = logging.getLogger(__name__)


class StaleAuthMaterialException(SeresparException):
    """The `AuthMaterial` exists but is expired, malformed or rejected."""


class QueryProcessException(SeresparException):
    """The `OriginQueryProcess` could not turn the `OriginQuery` into results.

    TODO: raised once `process_origin_query` checks that results actually came
    up; the base implementation only navigates.
    """


class PaginationControlMissingException(SeresparException):
    """The `NextPaginationTrigger` is not on the page.

    TODO: raised once `pagination_batches` steps through a
    `PaginationBatchStepper`; parsers log and retry today.
    """


class AccessBlockerEncounteredException(SeresparException):
    """A CAPTCHA, consent wall or unexpected login prompt is in the way.

    TODO: nothing detects these yet; they time out like any missing element.
    """

class ParsingSession():
    """The core orchestrator: it manages the main execution loop of one parsing run.

    A parsing session consists of:
        1. Opening a page
        2. Applying the `OriginQuery`, which opens a list of paginated search results
            - Preferably the `OriginUrl` contains everything so results come up directly. Where a site only takes its query through its own widgets, an `OriginQueryProcess` strategy fills them in; the builder injects it.
        3. Going through the results of the current `PaginationBatch`:
            - Generator gives control to caller so that they can do smt like:
                - Click certain elements of some results fitting a criteria
                - Extract key info from the search result
            - `ParserApp` is that caller in an assembled application; a test can be too.
        4. When the end of the batch is reached click the `NextPaginationTrigger` for the next batch
            - This is also done by the caller. Ofc this can work with infinite scrolling as well.
        5. We quit when we have reached `MaxDepth` in pagination. TODO: However we should be able to understand when we reach the end of pagination and quit there. Or after parsing a max number of entities.

    The session is the browser-side adapter: it owns the Playwright lifecycle
    and knows how one site is laid out. What to do with the results is the
    application's business -- see `ParserApp` in `app.py`, which drives the two
    generators below.

    TODO: the `SessionTracker` (limits, errors, "should we stop?") is not
    broken out yet; `num_failed_results` and the start/end times below are all
    the session tracks.
    """
    _start_time: datetime | None
    _end_time: datetime | None
    _browser: Browser
    _page: Page # playwright page object
    _auth_material_path: Path | str | None
    _origin_url: str
    _config: CoreConfig
    _origin_query_process: OriginQueryProcess
    num_failed_results: int

    def __init__(
            self,
            origin_url: str,
            auth_material_path: str | None = None,
            config: CoreConfig | None = None,
            origin_query_process: OriginQueryProcess | None = None) -> None:
        """`origin_url` is the base web address where the session enters the
        target website.

        `auth_material_path` points at the `AuthMaterial` to enter the site
        with. TODO: only a cookie file is supported, i.e. this is hardwired to
        what a `CookiePassiveFlow` would do; the `AuthFlow` hierarchy does not
        exist yet.

        `config` is the resolved configuration, injected by the builder. Only
        the `CoreConfig` layer -- window size, headless mode -- is anyone's
        business here; a parser's session subclass narrows the annotation to
        its own `EffectiveConfig` subclass and reads its own fields off it.
        Left out, the core layer is read from the environment
        (`CoreSettings`), which is what a session built by hand still gets.

        `origin_query_process` is the `OriginQueryProcess` strategy. Left out,
        the session just navigates to the `OriginUrl`."""
        self._auth_material_path = auth_material_path
        self._origin_url = origin_url
        self._config = config if config is not None else CoreSettings()
        self._origin_query_process = (
            origin_query_process
            if origin_query_process is not None
            else NavigateToOriginUrl(origin_url)
        )
        # TODO: can we make this a prop which can be set in real time?
        self._view_port = ViewportSize(
            width=self._config.viewport_width,
            height=self._config.viewport_height,
        )

    def __enter__(self) -> Self:
        self._start_time = datetime.now()
        self.num_failed_results = 0
        
        # get context and manually enter / exit instead of using with statement
        self._pw_ctx = sync_playwright()
        pw = self._pw_ctx.__enter__()

        logger.info(f"Launching chromium {'headless' if self._config.headless else 'headed'}")
        self._browser = pw.chromium.launch(headless=self._config.headless)
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
                raise StaleAuthMaterialException(
                    f"Unable to enter the site with the auth material at "
                    f"{self._auth_material_path}"
                ) from err

        self._page: Page = context.new_page()
        
        self.process_origin_query()

        return self # with pw, page, browser and whatever?


    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self._end_time = datetime.now()
        # prep a basic SessionReport somewhere

        self._browser.close()
        self._pw_ctx.__exit__()

    def process_origin_query(self) -> None:
        """Run the injected `OriginQueryProcess` against this session's page.

        Whatever it takes to get paginated search results on screen: usually
        just opening the `OriginUrl`, sometimes filling in the site's own
        filter widgets. Which of those happens is the strategy's business, not
        the session's -- see `serespar/ports.py` and `origin_query.py`.
        """
        self._origin_query_process.open_results(self._page)

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
