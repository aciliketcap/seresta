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
    ParserBuilder,
    SessionTracker,
    ParsingError,
    ParsingSession,
)
from serespar.config import ParserConfig, ProjectConfig, TaskConfig

logger = logging.getLogger(__name__)

STUB_INDEX_URL = "http://nginx/index.html"
STUB_DEFECTS_URL = "http://nginx/defects.html"

CARDS_TABLE = "#cards-table"
CARD_CELLS = "#cards-table td.card"
PAGINATION_LIST = "#pagi-list"

CARDS_PER_BATCH = 20
NUM_PAGINATION_BATCHES = 5

# Comfortably above the stub's own TABLE_DELAY_MS / CELL_DELAY_MS.
# TABLE_ is what a `PageSyncBarrier` would wait on, CELL_ a `ResultSyncBarrier`.
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


class TestParsingSessionError(Exception):
    __test__ = False


@dataclass
class ParsedCard:
    id: int
    name: str
    value: int


ParsedPaginationBatch = list[ParsedCard]


class TestRepo(AbstractBaseRepository[ParsedCard]):
    __test__ = False

    def __init__(self):
        self.cur_batch = ParsedPaginationBatch()
        self.batches: list[ParsedPaginationBatch] = []

    def add(self, parsed_entity: ParsedCard) -> None:
        self.cur_batch.append(parsed_entity)

    def next_pagination_batch(self):
        self.batches.append(copy(self.cur_batch))
        self.cur_batch = []

    def find_card_in_batch(self, entity_id: int, batch: ParsedPaginationBatch) -> ParsedCard | None:
        in_batch = [pc for pc in batch if pc.id == entity_id]
        if len(in_batch) > 1:
            raise ValueError(f"Duplicate cards with same id {entity_id}!")
        elif len(in_batch) == 1:
            return in_batch[0]
        else:
            return None

    def get(self, entity_id: int) -> ParsedCard | None:
        found: list[ParsedCard] = []
        if (in_cur_batch := self.find_card_in_batch(entity_id, self.cur_batch)):
            found.append(in_cur_batch)

        for batch in self.batches:
            if (in_batch := self.find_card_in_batch(entity_id, batch)):
                found.append(in_batch)

        if len(found) > 1:
            raise ValueError(f"Duplicate cards with same id {entity_id}!")
        elif len(found) == 1:
            return found[0]
        else:
            return None


# --------------------------------------------------------------------------
# Sessions
# --------------------------------------------------------------------------

class StubParsingSession(ParsingSession):
    """Base for both stub sessions; exposes the page so tests needn't poke _page."""

    __test__ = False

    @property
    def page(self) -> Page:
        return self._page

    def results_in_pagination_batch(self) -> Generator[tuple[Page, Locator], Any, Any]:
        raise NotImplementedError

    def pagination_batches(self, max_depth: int) -> Generator[int, Any, None]:
        raise NotImplementedError


class LazyCardsParsingSession(StubParsingSession):
    """Walks the lazily-rendered card table on ``index.html``.

    Same shape as the carwow session: result locators resolve before their
    contents arrive, so each cell is scrolled into view and then waited on.
    """

    __test__ = False

    def results_in_pagination_batch(self) -> Generator[tuple[Page, Locator], Any, Any]:
        # An inline `PageSyncBarrier`: the table itself is injected after the
        # load event, so wait for the batch layout to settle.
        self._page.locator(CARDS_TABLE).wait_for(
            state="attached", timeout=TABLE_LOAD_TIMEOUT_MS
        )

        cells = self._page.locator(CARD_CELLS)
        # Every cell exists once the skeleton is attached; only the contents
        # are lazy. Index with nth() rather than snapshotting via .all(),
        # because each cell's subtree is rewritten while we iterate.
        for ix in range(cells.count()):
            cell = cells.nth(ix)
            # An inline `ContentUnroller`: lower rows sit below the 1000px
            # viewport, and their IntersectionObserver won't fire until
            # they're scrolled to.
            cell.scroll_into_view_if_needed()
            # An inline `ResultSyncBarrier`.
            expect(cell).to_have_attribute(
                "data-loaded", "true", timeout=CELL_LOAD_TIMEOUT_MS
            )
            yield self._page, cell
            logger.info("Moving on to the next card")

    def find_next_pagination_trigger(
        self, pagination_list_locator: Locator, next_pagination_num: int
    ) -> Locator | None:
        for pagination_trigger in pagination_list_locator.locator("a").all():
            pagination_trigger_text = pagination_trigger.text_content()
            if not pagination_trigger_text:
                continue
            try:
                pagination_num = int(pagination_trigger_text.strip())
            except ValueError:
                continue

            if pagination_num == next_pagination_num:
                return pagination_trigger

        return None

    def pagination_batches(self, max_depth: int) -> Generator[int, Any, None]:
        """Yields the PaginationIndex 1..max_depth inclusive, clicking through in between.

        NOTE: this deliberately differs from the carwow session, which loops
        `range(1, max_depth)` and so never parses the last batch it lands
        on — and then still asks for a next pagination trigger that isn't there.
        """
        for pagination_index in range(1, max_depth + 1):
            yield pagination_index

            if pagination_index == max_depth:
                return

            next_pagination_trigger = self.find_next_pagination_trigger(
                self._page.locator(PAGINATION_LIST), pagination_index + 1
            )

            if not next_pagination_trigger:
                # TODO: this is where a `PaginationControlMissingException`
                # raised by serespar belongs, rather than a test-local error.
                raise TestParsingSessionError(
                    f"Couldn't move to the next pagination batch: {pagination_index + 1}"
                )

            next_pagination_trigger.click()
            # Pagination links are real hrefs, so this is a full navigation.
            self._page.wait_for_load_state("load")


class DefectsParsingSession(StubParsingSession):
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
        self._parsed_entity = ParsedCard(
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


class NeverSetsParsedEntityExtractor(CardExtractor):
    """Extracts fine but forgets to assign ``self._parsed_entity`` — silent data loss."""

    __test__ = False

    def extract_and_persist(self) -> None:
        self._extract_id()
        self._extract_name()


# --------------------------------------------------------------------------
# The application, assembled by the builder
# --------------------------------------------------------------------------

class StubSitesProjectConfig(ProjectConfig):
    """The project layer for the stub sites: no database anywhere.

    `ProjectConfig` keeps the db fields for every project, storage or not, so
    this states the ones it has no use for rather than leaving them required.
    """

    __test__ = False

    db_host: str = "no-database"
    db_name: str = "no-database"


class StubParserBuilder(ParserBuilder):
    """Composition root for the suite: the stub app, with nothing persisted.

    The layers are handed over rather than read from the environment, and the
    repository is a `TestRepo` that keeps everything in a list, so building the
    application here goes through exactly the code path production does.
    """

    __test__ = False

    project_config_cls = StubSitesProjectConfig
    # No env file feeds these; each test app passes its own layer objects.
    parser_config_cls = None
    task_config_cls = None
    extractor_cls = CardExtractor


class LazyCardsParserBuilder(StubParserBuilder):
    __test__ = False

    session_cls = LazyCardsParsingSession


class DefectsParserBuilder(StubParserBuilder):
    __test__ = False

    session_cls = DefectsParsingSession


def build_stub_app(
    builder_cls: type[StubParserBuilder],
    origin_url: str,
    repository: TestRepo | None = None,
    max_depth: int = NUM_PAGINATION_BATCHES,
):
    """One assembled stub application, ready to run or to step through."""
    builder = builder_cls(
        parser=ParserConfig(base_origin_url=origin_url),
        task=TaskConfig(task_id="stub-sites", max_depth=max_depth),
        repository=repository if repository is not None else TestRepo(),
    )
    return builder.build()


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
    with build_stub_app(DefectsParserBuilder, STUB_DEFECTS_URL) as app:
        page = app.session.page
        page.set_default_timeout(DEFECT_TIMEOUT_MS)
        yield page


@pytest.fixture
def repo() -> TestRepo:
    return TestRepo()


@pytest.fixture
def tracker() -> SessionTracker:
    return SessionTracker(1, 1, 1)


@pytest.fixture
def extractor(defects_page: Page, repo: TestRepo, tracker: SessionTracker):
    """Builds a CardExtractor over an arbitrary result locator, outside a `with`.

    The text_/url_ helpers are plain methods, so they can be exercised without
    entering the context manager.
    """
    def _build(result_locator: Locator) -> CardExtractor:
        return CardExtractor(repo, defects_page, result_locator, tracker)

    return _build


# --------------------------------------------------------------------------
# Happy path — lazy loading
# --------------------------------------------------------------------------

def test_stub_really_is_lazy() -> None:
    """Guard: if index.html ever renders eagerly, the happy path stops proving anything."""
    with build_stub_app(LazyCardsParserBuilder, STUB_INDEX_URL) as app:
        page = app.session.page

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
    repo = TestRepo()
    app = build_stub_app(LazyCardsParserBuilder, STUB_INDEX_URL, repository=repo)

    with app:
        # `run()` is the same loop; stepping through it is how this test gets
        # to close off a pagination batch in the repo as it goes.
        for _pagination_index in app.run_pagination_batches():
            repo.next_pagination_batch()

        assert app.session.num_failed_results == 0
        assert len(repo.batches) == NUM_PAGINATION_BATCHES

        for batch_ix, parsed_batch in enumerate(repo.batches):
            assert len(parsed_batch) == CARDS_PER_BATCH
            for result_ix, parsed_entity in enumerate(parsed_batch, start=1):
                expected_id = batch_ix * CARDS_PER_BATCH + result_ix
                assert parsed_entity.id == expected_id
                assert parsed_entity.value == expected_id
                assert parsed_entity.name == NAME_PERMS[expected_id - 1]

        # Nothing was dropped and nothing was double-counted.
        assert repo.get(1) is not None
        assert repo.get(NUM_PAGINATION_BATCHES * CARDS_PER_BATCH) is not None
        assert repo.get(NUM_PAGINATION_BATCHES * CARDS_PER_BATCH + 1) is None


# --------------------------------------------------------------------------
# BaseExtractor.__exit__ — what survives and what is discarded
# --------------------------------------------------------------------------

def test_valid_card_is_persisted(defects_page, repo, tracker) -> None:
    with CardExtractor(repo, defects_page, card(defects_page, "ok"), tracker) as xtor:
        xtor.extract_and_persist()

    assert repo.cur_batch == [ParsedCard(id=1, name="AAA", value=1)]


def test_critical_failure_propagates_and_discards_record(defects_page, repo, tracker) -> None:
    """__exit__ returns False on error, so the record never reaches the repo."""
    with pytest.raises(ExtractionCriticalError):
        with CardExtractor(repo, defects_page, card(defects_page, "empty-id"), tracker) as xtor:
            xtor.extract_and_persist()

    assert repo.cur_batch == []


def test_partial_record_is_discarded_not_half_written(defects_page, repo, tracker) -> None:
    """id and name parse fine, value doesn't — the whole card is still dropped."""
    with pytest.raises(ExtractionCriticalError):
        with CardExtractor(repo, defects_page, card(defects_page, "missing-value"), tracker) as xtor:
            xtor.extract_and_persist()

    assert repo.cur_batch == []
    assert repo.get(4) is None


def test_unset_parsed_entity_is_silently_not_persisted(defects_page, repo, tracker, caplog) -> None:
    """No exception, nothing persisted, only a CRITICAL log to show for it."""
    with caplog.at_level(logging.CRITICAL, logger="serespar.base_extractor"):
        with NeverSetsParsedEntityExtractor(
            repo, defects_page, card(defects_page, "ok"), tracker
        ) as xtor:
            xtor.extract_and_persist()

    assert repo.cur_batch == []
    assert any(rec.levelno == logging.CRITICAL for rec in caplog.records)


# --------------------------------------------------------------------------
# critical_info — wraps whatever went wrong, keeps the cause
# --------------------------------------------------------------------------

def test_critical_info_wraps_parsing_error(defects_page, repo, tracker) -> None:
    xtor = CardExtractor(repo, defects_page, card(defects_page, "empty-id"), tracker)

    with pytest.raises(ExtractionCriticalError) as excinfo:
        xtor._extract_id()

    assert isinstance(excinfo.value.__cause__, ParsingError)
    assert "_extract_id" in str(excinfo.value)
    assert "CardExtractor" in str(excinfo.value)


def test_critical_info_wraps_value_error(defects_page, repo, tracker) -> None:
    """The text extracts fine; int() is what fails."""
    xtor = CardExtractor(repo, defects_page, card(defects_page, "nan-id"), tracker)

    with pytest.raises(ExtractionCriticalError) as excinfo:
        xtor._extract_id()

    assert isinstance(excinfo.value.__cause__, ValueError)


def test_critical_info_wraps_playwright_timeout(defects_page, repo, tracker) -> None:
    """A selector that never resolves surfaces as a timeout, not a ParsingError."""
    xtor = CardExtractor(repo, defects_page, card(defects_page, "missing-value"), tracker)

    with pytest.raises(ExtractionCriticalError) as excinfo:
        xtor._extract_value()

    assert isinstance(excinfo.value.__cause__, PlaywrightTimeoutError)


def test_critical_info_reports_position_in_message(defects_page, repo) -> None:
    tracker = SessionTracker(1, 3, 7)
    xtor = CardExtractor(repo, defects_page, card(defects_page, "empty-id"), tracker)

    with pytest.raises(ExtractionCriticalError) as excinfo:
        xtor._extract_id()

    assert "result 7" in str(excinfo.value)
    assert "pagination batch 3" in str(excinfo.value)


# --------------------------------------------------------------------------
# noncrit_info — degrade instead of discard
# --------------------------------------------------------------------------

def test_noncrit_info_falls_back_and_still_persists(defects_page, repo, tracker, caplog) -> None:
    with caplog.at_level(logging.ERROR, logger="serespar.base_extractor"):
        with NonCriticalValueCardExtractor(
            repo, defects_page, card(defects_page, "missing-value"), tracker
        ) as xtor:
            xtor.extract_and_persist()

    assert repo.cur_batch == [ParsedCard(id=4, name="AAD", value=NONCRIT_FALLBACK)]
    assert any(rec.levelno == logging.ERROR for rec in caplog.records)


def test_noncrit_info_does_not_interfere_when_field_is_fine(defects_page, repo, tracker) -> None:
    with NonCriticalValueCardExtractor(
        repo, defects_page, card(defects_page, "ok"), tracker
    ) as xtor:
        xtor.extract_and_persist()

    assert repo.cur_batch == [ParsedCard(id=1, name="AAA", value=1)]


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


def test_url_falls_back_to_the_result_itself(defects_page, extractor) -> None:
    """With no link element passed, the result locator is treated as the anchor."""
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
