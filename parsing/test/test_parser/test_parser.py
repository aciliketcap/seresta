"""Integration tests for serespar against the nginx-served stub pages.

Two stubs back these tests:

* ``index.html``   – lazy-loading happy path. Neither the table nor any cell in
                     it exists at load time, so the session has to wait for
                     both, the same shape as carwow's lazily-filled turbo-frames.
* ``defects.html`` – static, deliberately malformed cards, one defect each,
                     driving every failure mode in ``serespar/base_extractor.py``.

Everything lives in this one module on purpose: ``test_parser/`` ships an
``__init__.py``, which makes ``from conftest import ...`` depend on how pytest
picks its rootdir inside the container.
"""

import logging
from copy import copy
from dataclasses import dataclass
from itertools import product
from string import ascii_uppercase
from time import sleep
from typing import Any, Generator

import pytest
from playwright.sync_api import Locator, Page, expect
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from pydantic_core import Url

from serespar import (
    AbstractBaseRepository,
    BaseExtractor,
    ExtractionCriticalError,
    ParseItemContext,
    ParsingError,
    ResultsParseSession,
)

logger = logging.getLogger(__name__)

STUB_INDEX_URL = "http://nginx/index.html"
STUB_DEFECTS_URL = "http://nginx/defects.html"

CARDS_TABLE = "#cards-table"
CARD_CELLS = "#cards-table td.card"
PAGI_LIST = "#pagi-list"

CARDS_PER_PAGE = 20
NUM_PAGES = 5

# Comfortably above the stub's own TABLE_DELAY_MS / CELL_DELAY_MS.
TABLE_LOAD_TIMEOUT_MS = 5_000
CELL_LOAD_TIMEOUT_MS = 5_000

# The negative tests aim at elements that never appear, so a Playwright timeout
# is the expected outcome, not a failure. Keep it short or the suite crawls.
DEFECT_TIMEOUT_MS = 1_000

# nginx and this container come up together; give it a moment before the first
# request. See the _wait_for_nginx fixture.
NGINX_STARTUP_WAIT_SECONDS = 3

# Expected names: 1 -> AAA, 2 -> AAB, ... matching cardName() in the stub.
NAME_PERMS = ["".join(perm) for perm in product(ascii_uppercase, repeat=3)][0:100]


class TestParseSessionError(Exception):
    __test__ = False


@dataclass
class ParsedCard:
    id: int
    name: str
    value: int


ParsedPage = list[ParsedCard]


class TestRepo(AbstractBaseRepository[ParsedCard]):
    __test__ = False

    def __init__(self):
        self.cur_page = ParsedPage()
        self.pages: list[ParsedPage] = []

    def add(self, seres: ParsedCard) -> None:
        self.cur_page.append(seres)

    def next_page(self):
        self.pages.append(copy(self.cur_page))
        self.cur_page = []

    def find_card_in_page(self, seres_id: int, page: ParsedPage) -> ParsedCard | None:
        in_page = [pc for pc in page if pc.id == seres_id]
        if len(in_page) > 1:
            raise ValueError(f"Duplicate cards with same id {seres_id}!")
        elif len(in_page) == 1:
            return in_page[0]
        else:
            return None

    def get(self, seres_id: int) -> ParsedCard | None:
        found: list[ParsedCard] = []
        if (in_cur_page := self.find_card_in_page(seres_id, self.cur_page)):
            found.append(in_cur_page)

        for page in self.pages:
            if (in_page := self.find_card_in_page(seres_id, page)):
                found.append(in_page)

        if len(found) > 1:
            raise ValueError(f"Duplicate cards with same id {seres_id}!")
        elif len(found) == 1:
            return found[0]
        else:
            return None


# --------------------------------------------------------------------------
# Sessions
# --------------------------------------------------------------------------

class StubParseSession(ResultsParseSession):
    """Base for both stub sessions; exposes the page so tests needn't poke _page."""

    __test__ = False

    @property
    def page(self) -> Page:
        return self._page

    def results_in_pagination(self) -> Generator[tuple[Page, Locator], Any, Any]:
        raise NotImplementedError

    def paginations_in_search_results(self, max_pagination: int) -> Generator[int, Any, None]:
        raise NotImplementedError


class LazyCardsParseSession(StubParseSession):
    """Walks the lazily-rendered card table on ``index.html``.

    Same shape as the carwow session: item locators resolve before their
    contents arrive, so each cell is scrolled into view and then waited on.
    """

    __test__ = False

    def results_in_pagination(self) -> Generator[tuple[Page, Locator], Any, Any]:
        # The table itself is injected after the load event.
        self._page.locator(CARDS_TABLE).wait_for(
            state="attached", timeout=TABLE_LOAD_TIMEOUT_MS
        )

        cells = self._page.locator(CARD_CELLS)
        # Every cell exists once the skeleton is attached; only the contents
        # are lazy. Index with nth() rather than snapshotting via .all(),
        # because each cell's subtree is rewritten while we iterate.
        for ix in range(cells.count()):
            cell = cells.nth(ix)
            # Lower rows sit below the 1000px viewport, and their
            # IntersectionObserver won't fire until they're scrolled to.
            cell.scroll_into_view_if_needed()
            expect(cell).to_have_attribute(
                "data-loaded", "true", timeout=CELL_LOAD_TIMEOUT_MS
            )
            yield self._page, cell
            logger.info("Moving on to the next card")

    def find_next_pagi_button(
        self, pagi_locator: Locator, next_pagi_num: int
    ) -> Locator | None:
        for pagi_button in pagi_locator.locator("a").all():
            pagi_str = pagi_button.text_content()
            if not pagi_str:
                continue
            try:
                pagi_num = int(pagi_str.strip())
            except ValueError:
                continue

            if pagi_num == next_pagi_num:
                return pagi_button

        return None

    def paginations_in_search_results(self, max_pagination: int) -> Generator[int, Any, None]:
        """Yields 1..max_pagination inclusive, clicking through in between.

        NOTE: this deliberately differs from the carwow session, which loops
        `range(1, max_pagination)` and so never parses the last page it lands
        on — and then still asks for a next-page button that isn't there.
        """
        for cur_page_num in range(1, max_pagination + 1):
            yield cur_page_num

            if cur_page_num == max_pagination:
                return

            next_pagi_button = self.find_next_pagi_button(
                self._page.locator(PAGI_LIST), cur_page_num + 1
            )

            if not next_pagi_button:
                raise TestParseSessionError(
                    f"Couldn't move to the next page: Page {cur_page_num + 1}"
                )

            next_pagi_button.click()
            # Pagination links are real hrefs, so this is a full navigation.
            self._page.wait_for_load_state("load")


class DefectsParseSession(StubParseSession):
    """Opens ``defects.html``. Iteration/pagination are unused by the negatives."""

    __test__ = False


# --------------------------------------------------------------------------
# Extractors
# --------------------------------------------------------------------------

class CardExtractor(BaseExtractor[TestRepo, ParsedCard]):
    """The straightforward extractor: every field is critical."""

    __test__ = False

    @BaseExtractor.critical_info
    def _extract_id(self) -> int:
        return int(self.text_at_selector(".card-id"))

    @BaseExtractor.critical_info
    def _extract_name(self) -> str:
        return self.text_at_selector(".card-name")

    @BaseExtractor.critical_info
    def _extract_value(self) -> int:
        return int(self.text_at_selector(".card-value"))

    def extract_and_persist(self) -> None:
        self._seres = ParsedCard(
            self._extract_id(),
            self._extract_name(),
            self._extract_value(),
        )


NONCRIT_FALLBACK = -1


class NonCriticalValueCardExtractor(CardExtractor):
    """``value`` degrades to a fallback instead of sinking the whole record."""

    __test__ = False

    @BaseExtractor.noncrit_info(error_value=NONCRIT_FALLBACK)
    def _extract_value(self) -> int:
        return int(self.text_at_selector(".card-value"))


class NeverSetsSeresExtractor(CardExtractor):
    """Extracts fine but forgets to assign ``self._seres`` — silent data loss."""

    __test__ = False

    def extract_and_persist(self) -> None:
        self._extract_id()
        self._extract_name()


# --------------------------------------------------------------------------
# Fixtures / helpers
# --------------------------------------------------------------------------

def card(page: Page, defect: str) -> Locator:
    """A card on defects.html, selected by its ``data-defect`` name."""
    return page.locator(f'{CARDS_TABLE} td.card[data-defect="{defect}"]')


@pytest.fixture(scope="session", autouse=True)
def _wait_for_nginx() -> None:
    # magic sleep until nginx is actually up and serving our test .html files.
    # Session-scoped so it costs 3s for the whole run, not 3s per test.
    sleep(NGINX_STARTUP_WAIT_SECONDS)


@pytest.fixture
def defects_page() -> Generator[Page, Any, None]:
    with DefectsParseSession(STUB_DEFECTS_URL, None) as session:
        session.page.set_default_timeout(DEFECT_TIMEOUT_MS)
        yield session.page


@pytest.fixture
def repo() -> TestRepo:
    return TestRepo()


@pytest.fixture
def ctx() -> ParseItemContext:
    return ParseItemContext(1, 1, 1)


@pytest.fixture
def extractor(defects_page: Page, repo: TestRepo, ctx: ParseItemContext):
    """Builds a CardExtractor over an arbitrary item locator, outside a `with`.

    The text_/url_ helpers are plain methods, so they can be exercised without
    entering the context manager.
    """
    def _build(item: Locator) -> CardExtractor:
        return CardExtractor(repo, defects_page, item, ctx)

    return _build


# --------------------------------------------------------------------------
# Happy path — lazy loading
# --------------------------------------------------------------------------

def test_stub_really_is_lazy() -> None:
    """Guard: if index.html ever renders eagerly, the happy path stops proving anything."""
    with LazyCardsParseSession(STUB_INDEX_URL, None) as session:
        page = session.page

        # goto() waited for `load`; the table is injected only after that.
        assert page.locator(CARDS_TABLE).count() == 0

        # Sample the first cell from inside the page, at the instant the table
        # attaches. Reading it back over the wire instead would race the stub's
        # CELL_DELAY_MS against a Playwright round trip -- a window this test
        # loses on a loaded machine, for reasons that say nothing about
        # whether the page is lazy.
        first_cell_at_attach = page.evaluate(
            """({ tableSel, cellSel, timeoutMs }) => new Promise(resolve => {
                const sample = () => {
                    if (!document.querySelector(tableSel)) return false;
                    const cell = document.querySelector(cellSel);
                    resolve({
                        loaded: cell.dataset.loaded ?? null,
                        idCount: cell.querySelectorAll('.card-id').length,
                    });
                    return true;
                };
                if (sample()) return;
                const obs = new MutationObserver(() => { if (sample()) obs.disconnect(); });
                obs.observe(document.body, { childList: true, subtree: true });
                // Never hang the suite if the table stops arriving altogether.
                setTimeout(() => { obs.disconnect(); resolve(null); }, timeoutMs);
            })""",
            {
                "tableSel": CARDS_TABLE,
                "cellSel": CARD_CELLS,
                "timeoutMs": TABLE_LOAD_TIMEOUT_MS,
            },
        )

        assert first_cell_at_attach is not None, "the table never attached"

        # Skeleton is attached but the cells are still empty.
        assert first_cell_at_attach["loaded"] is None
        assert first_cell_at_attach["idCount"] == 0

        expect(page.locator(CARD_CELLS).first).to_have_attribute(
            "data-loaded", "true", timeout=CELL_LOAD_TIMEOUT_MS
        )


def test_integ_lazy_happy_path() -> None:
    with LazyCardsParseSession(STUB_INDEX_URL, None) as session:
        repo = TestRepo()
        for cur_pagi_num in session.paginations_in_search_results(NUM_PAGES):
            cur_item_num = 0
            for page, card_loc in session.results_in_pagination():
                cur_item_num += 1
                ctx = ParseItemContext(1, cur_pagi_num, cur_item_num)
                try:
                    with CardExtractor(repo, page, card_loc, ctx) as xtor:
                        xtor.extract_and_persist()
                except Exception:
                    session.num_failed_results += 1
            repo.next_page()

        assert session.num_failed_results == 0
        assert len(repo.pages) == NUM_PAGES

        for page_ix, parsed_page in enumerate(repo.pages):
            assert len(parsed_page) == CARDS_PER_PAGE
            for seres_ix, seres in enumerate(parsed_page, start=1):
                expected_id = page_ix * CARDS_PER_PAGE + seres_ix
                assert seres.id == expected_id
                assert seres.value == expected_id
                assert seres.name == NAME_PERMS[expected_id - 1]

        # Nothing was dropped and nothing was double-counted.
        assert repo.get(1) is not None
        assert repo.get(NUM_PAGES * CARDS_PER_PAGE) is not None
        assert repo.get(NUM_PAGES * CARDS_PER_PAGE + 1) is None


# --------------------------------------------------------------------------
# BaseExtractor.__exit__ — what survives and what is discarded
# --------------------------------------------------------------------------

def test_valid_card_is_persisted(defects_page, repo, ctx) -> None:
    with CardExtractor(repo, defects_page, card(defects_page, "ok"), ctx) as xtor:
        xtor.extract_and_persist()

    assert repo.cur_page == [ParsedCard(id=1, name="AAA", value=1)]


def test_critical_failure_propagates_and_discards_record(defects_page, repo, ctx) -> None:
    """__exit__ returns False on error, so the record never reaches the repo."""
    with pytest.raises(ExtractionCriticalError):
        with CardExtractor(repo, defects_page, card(defects_page, "empty-id"), ctx) as xtor:
            xtor.extract_and_persist()

    assert repo.cur_page == []


def test_partial_record_is_discarded_not_half_written(defects_page, repo, ctx) -> None:
    """id and name parse fine, value doesn't — the whole card is still dropped."""
    with pytest.raises(ExtractionCriticalError):
        with CardExtractor(repo, defects_page, card(defects_page, "missing-value"), ctx) as xtor:
            xtor.extract_and_persist()

    assert repo.cur_page == []
    assert repo.get(4) is None


def test_unset_seres_is_silently_not_persisted(defects_page, repo, ctx, caplog) -> None:
    """No exception, nothing persisted, only a CRITICAL log to show for it."""
    with caplog.at_level(logging.CRITICAL, logger="serespar.base_extractor"):
        with NeverSetsSeresExtractor(
            repo, defects_page, card(defects_page, "ok"), ctx
        ) as xtor:
            xtor.extract_and_persist()

    assert repo.cur_page == []
    assert any(rec.levelno == logging.CRITICAL for rec in caplog.records)


# --------------------------------------------------------------------------
# critical_info — wraps whatever went wrong, keeps the cause
# --------------------------------------------------------------------------

def test_critical_info_wraps_parsing_error(defects_page, repo, ctx) -> None:
    xtor = CardExtractor(repo, defects_page, card(defects_page, "empty-id"), ctx)

    with pytest.raises(ExtractionCriticalError) as excinfo:
        xtor._extract_id()

    assert isinstance(excinfo.value.__cause__, ParsingError)
    assert "_extract_id" in str(excinfo.value)
    assert "CardExtractor" in str(excinfo.value)


def test_critical_info_wraps_value_error(defects_page, repo, ctx) -> None:
    """The text extracts fine; int() is what fails."""
    xtor = CardExtractor(repo, defects_page, card(defects_page, "nan-id"), ctx)

    with pytest.raises(ExtractionCriticalError) as excinfo:
        xtor._extract_id()

    assert isinstance(excinfo.value.__cause__, ValueError)


def test_critical_info_wraps_playwright_timeout(defects_page, repo, ctx) -> None:
    """A selector that never resolves surfaces as a timeout, not a ParsingError."""
    xtor = CardExtractor(repo, defects_page, card(defects_page, "missing-value"), ctx)

    with pytest.raises(ExtractionCriticalError) as excinfo:
        xtor._extract_value()

    assert isinstance(excinfo.value.__cause__, PlaywrightTimeoutError)


def test_critical_info_reports_position_in_message(defects_page, repo) -> None:
    ctx = ParseItemContext(1, 3, 7)
    xtor = CardExtractor(repo, defects_page, card(defects_page, "empty-id"), ctx)

    with pytest.raises(ExtractionCriticalError) as excinfo:
        xtor._extract_id()

    assert "item 7" in str(excinfo.value)
    assert "pagi 3" in str(excinfo.value)


# --------------------------------------------------------------------------
# noncrit_info — degrade instead of discard
# --------------------------------------------------------------------------

def test_noncrit_info_falls_back_and_still_persists(defects_page, repo, ctx, caplog) -> None:
    with caplog.at_level(logging.ERROR, logger="serespar.base_extractor"):
        with NonCriticalValueCardExtractor(
            repo, defects_page, card(defects_page, "missing-value"), ctx
        ) as xtor:
            xtor.extract_and_persist()

    assert repo.cur_page == [ParsedCard(id=4, name="AAD", value=NONCRIT_FALLBACK)]
    assert any(rec.levelno == logging.ERROR for rec in caplog.records)


def test_noncrit_info_does_not_interfere_when_field_is_fine(defects_page, repo, ctx) -> None:
    with NonCriticalValueCardExtractor(
        repo, defects_page, card(defects_page, "ok"), ctx
    ) as xtor:
        xtor.extract_and_persist()

    assert repo.cur_page == [ParsedCard(id=1, name="AAA", value=1)]


# --------------------------------------------------------------------------
# text_at_selector / text_at_locator
# --------------------------------------------------------------------------

def test_text_at_selector_empty_element_raises_parsing_error(defects_page, extractor) -> None:
    xtor = extractor(card(defects_page, "empty-id"))

    with pytest.raises(ParsingError, match="did not yield a string"):
        xtor.text_at_selector(".card-id")


def test_text_at_selector_missing_element_raises_timeout(defects_page, extractor) -> None:
    """`if not maybe_str` never gets a look in — Playwright times out first."""
    xtor = extractor(card(defects_page, "missing-value"))

    with pytest.raises(PlaywrightTimeoutError):
        xtor.text_at_selector(".card-value")


def test_text_at_selector_whitespace_only_returns_empty_string(defects_page, extractor) -> None:
    """Documents current behaviour: "   " is truthy, so it passes the guard and
    strips down to "". An empty element raises but a blank one doesn't."""
    xtor = extractor(card(defects_page, "whitespace-name"))

    assert xtor.text_at_selector(".card-name") == ""


def test_text_at_selector_takes_first_of_duplicates(defects_page, extractor) -> None:
    xtor = extractor(card(defects_page, "duplicate-id"))

    assert xtor.text_at_selector(".card-id") == "11"


def test_text_at_locator_empty_element_raises_parsing_error(defects_page, extractor) -> None:
    xtor = extractor(card(defects_page, "empty-id"))
    locator = card(defects_page, "empty-id").locator(".card-id")

    with pytest.raises(ParsingError, match="did not yield a string"):
        xtor.text_at_locator(locator)


def test_text_at_locator_strips_surrounding_whitespace(defects_page, extractor) -> None:
    xtor = extractor(card(defects_page, "ok"))
    locator = card(defects_page, "ok").locator(".card-name")

    assert xtor.text_at_locator(locator) == "AAA"


# --------------------------------------------------------------------------
# try_href_attr / url_from_link_elt
# --------------------------------------------------------------------------

def test_url_from_link_elt_reads_absolute_href(defects_page, extractor) -> None:
    xtor = extractor(card(defects_page, "link-ok"))
    link = card(defects_page, "link-ok").locator("a.card-link")

    assert xtor.url_from_link_elt(link) == Url("https://example.com/cards/7")


def test_url_falls_back_to_the_item_itself(defects_page, extractor) -> None:
    """With no link element passed, the item locator is treated as the anchor."""
    link = card(defects_page, "link-ok").locator("a.card-link")
    xtor = extractor(link)

    assert xtor.url_from_link_elt() == Url("https://example.com/cards/7")


def test_url_missing_href_attribute_raises_parsing_error(defects_page, extractor) -> None:
    xtor = extractor(card(defects_page, "link-no-href"))
    link = card(defects_page, "link-no-href").locator("a.card-link")

    with pytest.raises(ParsingError, match="Unable to get the URL"):
        xtor.url_from_link_elt(link)


def test_url_empty_href_raises_parsing_error(defects_page, extractor) -> None:
    xtor = extractor(card(defects_page, "link-empty-href"))
    link = card(defects_page, "link-empty-href").locator("a.card-link")

    with pytest.raises(ParsingError, match="Unable to get the URL"):
        xtor.url_from_link_elt(link)


def test_url_unresolvable_link_element_raises_parsing_error(defects_page, extractor) -> None:
    """get_attribute() itself blows up — the first except branch in try_href_attr."""
    xtor = extractor(card(defects_page, "ok"))
    missing_link = card(defects_page, "ok").locator("a.no-such-link")

    with pytest.raises(ParsingError, match="Unable to read"):
        xtor.url_from_link_elt(missing_link)


def test_url_relative_href_without_base_raises_parsing_error(defects_page, extractor) -> None:
    """pydantic's Url rejects a relative href when base_url is left empty."""
    xtor = extractor(card(defects_page, "link-relative"))
    link = card(defects_page, "link-relative").locator("a.card-link")

    with pytest.raises(ParsingError, match="into a valid URL"):
        xtor.url_from_link_elt(link)


def test_url_relative_href_with_base_url_resolves(defects_page, extractor) -> None:
    xtor = extractor(card(defects_page, "link-relative"))
    link = card(defects_page, "link-relative").locator("a.card-link")

    assert xtor.url_from_link_elt(
        link, base_url="https://example.com"
    ) == Url("https://example.com/cards/10")
