from copy import copy
from playwright.sync_api import Page, Locator
from typing import Generator, Any
from serespar import ResultsParseSession, BaseExtractor, ParseItemContext
import pytest
import logging
from dataclasses import dataclass
from string import ascii_uppercase
from itertools import product

from serespar.base_repos import AbstractBaseRepository

logger = logging.getLogger(__name__)

class TestParseSessionError(Exception):
    __test__ = False

@dataclass
class ParsedCard():
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
            raise ValueError("Duplicate cards with same id {seres_id}!")
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
            raise ValueError("Duplicate cards with same id {seres_id}!")
        elif len(found) == 1:
            return found[0]
        else:
            return None

class TestParseSession(ResultsParseSession):
    __test__ = False

    def __init__(self, target: str, cookie_path: str | None = None) -> None:
        super().__init__(target, cookie_path)
    
    def results_in_pagination(self) -> Generator[tuple[Page, Locator], Any, Any]:
        cards_rows_locator = self._page.locator("#cards-table tr")
        for card_row in cards_rows_locator.all():
            for card in card_row.locator("td").all():
                yield self._page, card
                logger.info("Moving on to the next card")

    def find_next_pagi_button(self, pagi_locator: Locator, next_pagi_num: int) -> Locator | None:
        pagi_num = None
        for pagi_button in pagi_locator.locator('a').all():
            pagi_str = pagi_button.text_content()
            if pagi_str:
                try:
                    pagi_num = int(pagi_str)
                except ValueError:
                    continue

                if pagi_num == next_pagi_num:
                    break

        if pagi_num:
            return pagi_button
        else:
            return None

    def paginations_in_search_results(self, max_pagination: int) -> Generator[int, Any, None]:
        for cur_page_num in range(1, max_pagination):
            yield cur_page_num

            next_pagi_button = self.find_next_pagi_button(
                self._page.locator("#pagi-list"),
                cur_page_num + 1)
            
            if not next_pagi_button:
                raise TestParseSessionError(f"Couldn't move to the next page: Page {cur_page_num+1}")
            else:                
                next_pagi_button.click()

class TestCardExtractor(BaseExtractor[TestRepo, ParsedCard]):
    __test__ = False
    @BaseExtractor.critical_info
    def _extract_id(self) -> int:
        return int(self.text_at_selector('.card-id'))

    @BaseExtractor.critical_info
    def _extract_name(self) -> str:
        return self.text_at_selector('.card-name')
    
    @BaseExtractor.critical_info
    def _extract_value(self) -> int:
        return int(self.text_at_selector('.card-value'))

    def extract_and_persist(self) -> None:
        self._seres = ParsedCard(
            self._extract_id(),
            self._extract_name(),
            self._extract_value()
        )
        print(self._seres)

# For validation
NAME_PERMS = ["".join(perm) for perm in product(ascii_uppercase, repeat=3)][0:100]
CARDS_PER_PAGE = 20

def test_integ() -> None:
    with TestParseSession("http://nginx/index.html", None) as session:
        repo = TestRepo()
        for cur_pagi_num in session.paginations_in_search_results(5):
            cur_item_num = 0
            for page, card in session.results_in_pagination():
                cur_item_num += 1
                ctx = ParseItemContext(
                    1,
                    cur_pagi_num,
                    cur_item_num
                )
                try:
                    with TestCardExtractor(
                        repo,
                        page,
                        card,
                        ctx
                    ) as xtor:
                        xtor.extract_and_persist()
                except Exception:
                    session.num_failed_results += 1
            # for testing purposes only
            repo.next_page()

        # assert scraped data from repo
        for page_ix, page in enumerate(repo.pages):
            assert len(page) == CARDS_PER_PAGE
            for seres_ix, seres in enumerate(page, start = 1):
                assert seres.id == page_ix * CARDS_PER_PAGE + seres_ix

 

    

