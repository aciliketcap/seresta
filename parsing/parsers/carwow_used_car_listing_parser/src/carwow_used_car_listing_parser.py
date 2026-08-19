import locale
from email.base64mime import body_decode
from typing import Any, Generator
from playwright.sync_api import Locator, Page, TimeoutError
from base_used_car_listing_parser import BaseUsedCarListingParsingSession, Source
import logging
from time import sleep # for sleeping random amounts of time between clicks

from .config import carwow_config

logger = logging.getLogger(__name__)

CARWOW_SEARCH_SELECTORS = {
    "CAR_CARDS_CONTAINER": "turbo-frame#stock_cars_v2_cards",
    "CAR_CARDS": "turbo-frame#stock_cars_v2_cards div.deal-card",
    "CAR_CARD_FRAMES": "turbo-frame#stock_cars_v2_cards turbo-frame",
    "PAGINATION_LIST": "div.pagination__page a"
}

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
class CarWowParsingSession(BaseUsedCarListingParsingSession):
    SOURCE = Source.CARWOW

    def results_in_pagination_batch(self) -> Generator[tuple[Page, Locator], Any, Any]:
        # TODO: unfortunately this is not working, results are loaded into the DOM lazyly. We need to approach this more like an infinite scroll, or at least "move on to the next and scroll into view until depleted"
        # TODO: another hacky approach would be to scroll to bottom and wait for a while

        # car card contents (except the ad cards) are loaded lazily. At page load we have all the locators but we need to wait for contents to load dynamically.
        # https://scrapeops.io/playwright-web-scraping-playbook/nodejs-playwright-waiting-page-element-load/

        car_card_frames_locator = self._page.locator(CARWOW_SEARCH_SELECTORS["CAR_CARD_FRAMES"])
        for car_card_frame in car_card_frames_locator.all():
            # An inline `ContentUnroller`.
            car_card_frame.scroll_into_view_if_needed()
            frame_id = car_card_frame.get_attribute('id')
            if frame_id:
                # An inline `ResultSyncBarrier`: try to make sure frame contents are loaded
                for i in range(carwow_config().result_sync_retries):
                    try:
                        # if false waits until timeout and throws
                        self._page.wait_for_function(
                            expression=js_frame_load_checker,
                            arg=frame_id,
                            timeout=carwow_config().result_sync_timeout_ms)
                    except TimeoutError:
                        pass # just retry

            # otherwise just try to parse
            yield self._page, car_card_frame
            logger.debug("moving on to the next card")

    def step_to_next_pagination_batch(self, pagination_index, pagination_list_locator) -> bool:
        """The `PaginationBatchStepper`: find the `NextPaginationTrigger` and click it."""
        for pagination_trigger in pagination_list_locator.all():
            pagination_trigger_text = pagination_trigger.text_content().strip()

            if pagination_trigger_text == str(pagination_index + 1):
                pagination_trigger.click()
                wait_seconds = carwow_config().new_page_load_wait_seconds
                logger.debug(f"moved to pagination batch {pagination_index + 1}, sleeping {wait_seconds}")
                sleep(wait_seconds)
                self._page.wait_for_load_state()
                # TODO: we need to check smt else to make sure SPA style new pagination content is loaded! Smt similar to the one in results_in_pagination_batch
                return True
        return False

    def pagination_batches(self, max_depth: int) -> Generator[int, Any, None]:
        for pagination_index in range(1, max_depth):
            # An inline `PageSyncBarrier`: make sure the batch layout is there
            # before attempting to paginate further.
            self._page.locator(CARWOW_SEARCH_SELECTORS["CAR_CARDS_CONTAINER"]).wait_for()

            yield pagination_index

            # TODO: this is broken, doesn't make sure a new PaginationBatch is loaded, just keeps parsing the existing one over and over if the new one doesn't load!
            pagination_list_locator = self._page.locator(CARWOW_SEARCH_SELECTORS["PAGINATION_LIST"])
            # TODO: a fixed sleep, not the glossary's `RetryWithBackoff`.
            for i in range(carwow_config().max_next_pagination_batch_retries):
                if self.step_to_next_pagination_batch(pagination_index, pagination_list_locator):
                    break
                else:
                    logger.error("Unable to move to next pagination batch %s, retrying... (%s)", pagination_index+1, i)
                    sleep(carwow_config().pagination_retry_sleep_seconds)


    def process_origin_query(self) -> None:
        """The `OriginQueryProcess` for carwow: it fills the filter forms by hand
        rather than compiling the `OriginQuery` into a URL.

        Every value it types comes from the `OriginQuery` of the resolved
        config; the pause after each interaction is the parser layer's
        `form_settle_seconds`.
        """
        super().process_origin_query()

        origin_query = carwow_config().origin_query
        settle = carwow_config().form_settle_seconds

        # TODO: these input elts are also lazily loaded
        self._page.locator("input#location-desktop").fill(origin_query.postcode)
        sleep(settle)
        self._page.get_by_text("Set location").click()
        sleep(settle)
        logger.info("location set")

        self._page.locator("select#price-gte-desktop").select_option(str(origin_query.price_min))
        sleep(settle)
        self._page.locator("select#price-lte-desktop").select_option(str(origin_query.price_max))
        sleep(settle)
        logger.info("price set to %s - %s", origin_query.price_min, origin_query.price_max)

        age_loc = self._page.locator("li#age-desktop")
        age_loc.click()
        age_from_opts = age_loc.locator("select#age-gte-desktop option").all()
        # TODO: make this base method, also what if value is not in any of the options?
        age_from_opt_value = [opt.get_attribute('value') for opt in age_from_opts if f"{origin_query.age_from} " in opt.text_content().strip() ][0]
        age_loc.locator("select#age-gte-desktop").select_option(age_from_opt_value)
        sleep(settle)
        logger.info("age from set to %s", origin_query.age_from)

        age_to_opts = age_loc.locator("select#age-lte-desktop option").all()
        age_to_opt_value = [opt.get_attribute('value') for opt in age_to_opts if f"{origin_query.age_to} " in opt.text_content().strip() ][0]
        age_loc.locator("select#age-lte-desktop").select_option(age_to_opt_value)
        sleep(settle)
        logger.info("age to set to %s", origin_query.age_to)

        self._page.locator("li#fuel_type-desktop").click()
        for fuel_type in origin_query.fuel_types:
            self._page.get_by_label(fuel_type).first.click()
            sleep(settle)
        logger.info("fuel to set to %s", origin_query.fuel_types)

        self._page.locator("li#gearbox-desktop").click()
        self._page.locator("li#gearbox-desktop").get_by_text(origin_query.transmission).first.click()
        logger.info("transmission to set to %s", origin_query.transmission)

        logger.info("Initiated the search.")

        # TODO: putting this here for now:
        # select price, make, model, mileage, year, engine_size, url from raw_used_car_listing where transmission = 'Automatic' order by price;
        # select count(id) from raw_used_car_listing where transmission = 'Automatic'
