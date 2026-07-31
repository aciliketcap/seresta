from pydantic.dataclasses import dataclass
import locale
from email.base64mime import body_decode
from typing import Any, Generator
from playwright.sync_api import Locator, Page, TimeoutError
from base_used_car_listing_parser import BaseUsedCarListingParseSession, Source
import logging
from time import sleep # for sleeping random amounts of time between clicks

logger = logging.getLogger(__name__)

# TODO: this is per parser cookies file, move this down to serespar module once I figure out how to do per task cookies properly
COOKIES_FILE = "/run/secrets/parser_cookies"

MAX_NEXT_PAGI_RETRIES = 3
NEW_PAGE_LOAD_WAIT_SECONDS = 6

CARWOW_SEARCH_SELECTORS = {
    "CAR_CARDS_CONTAINER": "turbo-frame#stock_cars_v2_cards",
    "CAR_CARDS": "turbo-frame#stock_cars_v2_cards div.deal-card",
    "CAR_CARD_FRAMES": "turbo-frame#stock_cars_v2_cards turbo-frame",
    "PAGINATION_LIST": "div.pagination__page a"
}

@dataclass
class search():
    postcode: str


# NEVER COMMIT THIS, put this into a config file!!!
s = search(
    "SW20 8JP"
)

js_frame_load_checker:str = '''
(frameId) => {
  // Look up the turbo frame by id
  const frame = document.getElementById(frameId);
  if (!frame || !frame.hasAttribute('complete')) {
    return false; // no element with that id or not yet loaded
  }

  // First direct div child
  const cardDiv = frame.querySelector(':scope > div');
  if (!cardDiv) {
    return false; // no card div inside
  }

  return cardDiv.classList.contains('deal-card')
      && !cardDiv.classList.contains('deal-card--placeholder');
}
'''


# TODO: this class's methods need to be abstracted away into serespar, just like extractors. Also they need to be made more robust!
class CarWowParseSession(BaseUsedCarListingParseSession):
    SOURCE = Source.CARWOW

    def results_in_pagination(self) -> Generator[tuple[Page, Locator], Any, Any]:
        # TODO: unfortunately this is not working, results are loaded into the DOM lazyly. We need to approach this more like an infinite scroll, or at least "move on to the next and scroll into view until depleted"
        # TODO: another hacky approach would be to scroll to bottom and wait for a while

        # car card contents (except the ad cards) are loaded lazily. At page load we have all the locators but we need to wait for contents to load dynamically.
        # https://scrapeops.io/playwright-web-scraping-playbook/nodejs-playwright-waiting-page-element-load/

        car_card_frames_locator = self._page.locator(CARWOW_SEARCH_SELECTORS["CAR_CARD_FRAMES"])
        for car_card_frame in car_card_frames_locator.all():
            car_card_frame.scroll_into_view_if_needed()
            frame_id = car_card_frame.get_attribute('id')
            if frame_id:
                # try to make sure frame contents are loaded
                for i in range(3):
                    try:
                        # if false waits until timeout and throws
                        self._page.wait_for_function(
                            expression=js_frame_load_checker,
                            arg=frame_id,
                            timeout=1000)
                    except TimeoutError:
                        pass # just retry

            # otherwise just try to parse
            yield self._page, car_card_frame
            logger.debug("moving on to the next card")

    def click_and_load_next_pagi(self, cur_page_num, pagi_list_locator) -> bool:
        for pagi in pagi_list_locator.all():
            pagi_text = pagi.text_content().strip()

            if pagi_text == str(cur_page_num + 1):
                pagi.click()
                logger.debug(f"moved to page {cur_page_num + 1}, sleeping {NEW_PAGE_LOAD_WAIT_SECONDS}")
                sleep(NEW_PAGE_LOAD_WAIT_SECONDS)
                self._page.wait_for_load_state()
                # TODO: we need to check smt else to make sure SPA style new pagination content is loaded! Smt similar to the one in results_in_pagination
                return True
        return False

    def paginations_in_search_results(self, max_pagination: int) -> Generator[int, Any, None]:
        for cur_page_num in range(1, max_pagination):
            # make sure initial results are there before attempting to paginate further
            self._page.locator(CARWOW_SEARCH_SELECTORS["CAR_CARDS_CONTAINER"]).wait_for()

            yield cur_page_num

            # TODO: this is broken, doesn't make sure a new pagination is loaded, just keeps parsing the existing page over and over if new one doesn't load!
            pagi_list_locator = self._page.locator(CARWOW_SEARCH_SELECTORS["PAGINATION_LIST"])
            for i in range(MAX_NEXT_PAGI_RETRIES):
                if self.click_and_load_next_pagi(cur_page_num, pagi_list_locator):
                    break
                else:
                    logger.error("Unable to move to next pagi %s, retrying... (%s)", cur_page_num+1, i)
                    sleep(1)


    def initiate_search(self) -> None:
        # TODO: pass in search params from config
        super().initiate_search()

        # TODO: these input elts are also lazily loaded
        self._page.locator("input#location-desktop").fill(s.postcode)
        sleep(2)
        self._page.get_by_text("Set location").click()
        sleep(2)
        logger.info("location set")

        self._page.locator("select#price-gte-desktop").select_option("10000")
        sleep(2)
        self._page.locator("select#price-lte-desktop").select_option("18000")
        sleep(2)
        logger.info("price set to ... - ...")

        age_loc = self._page.locator("li#age-desktop")
        age_loc.click()
        age_from_opts = age_loc.locator("select#age-gte-desktop option").all()
        # TODO: make this base method, also what if value is not in any of the options?
        age_from_2020_opt_value = [opt.get_attribute('value') for opt in age_from_opts if "2020 " in opt.text_content().strip() ][0]
        age_loc.locator("select#age-gte-desktop").select_option(age_from_2020_opt_value)
        sleep(2)
        logger.info("age from set to ...")

        age_to_opts = age_loc.locator("select#age-lte-desktop option").all()
        age_to_2024_opt_value = [opt.get_attribute('value') for opt in age_to_opts if "2024 " in opt.text_content().strip() ][0]
        age_loc.locator("select#age-lte-desktop").select_option(age_to_2024_opt_value)
        sleep(2)
        logger.info("age to set to ...")

        self._page.locator("li#fuel_type-desktop").click()
        self._page.get_by_label("Petrol").first.click()
        sleep(2)
        self._page.get_by_label("Hybrid").first.click()
        sleep(2)
        logger.info("fuel to set to ...")

        self._page.locator("li#gearbox-desktop").click()
        self._page.locator("li#gearbox-desktop").get_by_text("Automatic").first.click()
        logger.info("transmission to set to ...")

        logger.info("Initiated the search.")

        # TODO: putting this here for now:
        # select price, make, model, mileage, year, engine_size, url from raw_used_car_listing where transmission = 'Automatic' order by price;
        # select count(id) from raw_used_car_listing where transmission = 'Automatic'
