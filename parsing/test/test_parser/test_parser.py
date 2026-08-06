from playwright.sync_api import Page, Locator
from typing import Generator, Any
from serespar import ResultsParseSession
from turtle import st
# import pytest
import logging
from dataclasses import dataclass

from serespar.base_repos import AbstractBaseRepository

logger = logging.getLogger(__name__)

@dataclass
class ParsedCard():
    id: int
    name: str
    value: int

ParsedPage = list[ParsedCard]

class TestRepo(AbstractBaseRepository[ParsedCard]):
    def __init__(self):
        self.cur_page = ParsedPage()
        self.pages: list[ParsedPage] = []

    def add(self, seres: ParsedCard) -> None:
        self.cur_page.append(seres)

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
    def __init__(self, target: str, cookie_path: str | None = None) -> None:
        super().__init__(target, cookie_path)
    
    def results_in_pagination(self) -> Generator[tuple[Page, Locator], Any, Any]:
        cards_rows_locator = self._page.locator("cards-table.tr")
        for card_row in cards_rows_locator:
            for card in card_row.locator("td"):
                yield self._page, card
                logger.info("Moving on to the next card")

    def paginations_in_search_results(self, max_pagination: int) -> Generator[int, Any, None]:
        for cur_page_num in range(1, max_pagination):
            for pagi_elt = self._page.locator("pagi_list"):
                pagi_str = pagi_elt.text_content()
                try:
                    pagi_num = int(pagi_str)
                except ValueError:
                    continue

                if pagi_num == cur_page_num + 1:
                    pagi_elt.click()
                    break

# def test_integ() -> None:
#     pass
    

