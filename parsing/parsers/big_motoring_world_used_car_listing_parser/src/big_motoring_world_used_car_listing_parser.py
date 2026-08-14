from typing import Any, Generator
from playwright.sync_api import Locator, Page
from base_used_car_listing_parser import BaseUsedCarListingParsingSession, Source
import logging
from time import sleep # for sleeping random amounts of time between clicks

logger = logging.getLogger(__name__)

NEW_PAGE_LOAD_WAIT_SECONDS = 2

BMW_SEARCH_SELECTORS = {
    "CAR_CARDS": "div#car-results a.car-card",
    "PAGINATION_LIST": "div#pagination-container div.page-number",
    "AD_CARD_CLASS": "car-info-card"
}

class BigMotoringWorldParsingSession(BaseUsedCarListingParsingSession):
    SOURCE = Source.BIG_MOTORING_WORLD

    def results_in_pagination_batch(self) -> Generator[tuple[Page, Locator], Any, Any]:
        car_cards_locator = self._page.locator(BMW_SEARCH_SELECTORS["CAR_CARDS"])
        for car_card in car_cards_locator.all():
            # skip if the class has car-info-card, it is used for ads
            card_classes = car_card.get_attribute("class").split()
            if BMW_SEARCH_SELECTORS["AD_CARD_CLASS"] in card_classes:
                logger.debug("skipping ad card")
                continue

            car_card.scroll_into_view_if_needed()
            yield self._page, car_card
            sleep(1)
            logger.debug("moving on to the next card")

    def pagination_batches(self, max_depth: int) -> Generator[int, Any, None]:
        for pagination_index in range(1, max_depth):

            yield pagination_index

            pagination_list_locator = self._page.locator(BMW_SEARCH_SELECTORS["PAGINATION_LIST"])
            for pagination_trigger in pagination_list_locator.all():
                pagination_trigger_text = pagination_trigger.text_content().strip()
                logger.debug(f"pagination trigger number is {pagination_trigger_text}")

                if pagination_trigger_text == str(pagination_index + 1):
                    pagination_trigger.click()
                    break

            self._page.wait_for_load_state()
            logger.debug(f"moved to pagination batch {pagination_index + 1}, sleeping {NEW_PAGE_LOAD_WAIT_SECONDS}")
            sleep(NEW_PAGE_LOAD_WAIT_SECONDS)
