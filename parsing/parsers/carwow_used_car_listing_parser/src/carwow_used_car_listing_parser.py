"""carwow's `ParsingSession`: how this site's search results are walked.

Only the traversal lives here now. What the search *is* went to
`carwow_origin_query.py`, what the numbers are went to `config.py`, and what to
do with each result is the application's business -- see `serespar/app.py`.

TODO: this class's methods need to be abstracted away into serespar, just like
extractors. Also they need to be made more robust!
"""

import logging
from time import sleep  # for sleeping random amounts of time between clicks
from typing import Any, Generator

from playwright.sync_api import Locator, Page, TimeoutError
from serespar import ParsingSession

from .config import CarWowConfig

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


class CarWowParsingSession(ParsingSession):
    """Walks the lazily-filled turbo frames of a carwow search.

    The builder injects the resolved `CarWowConfig`, so every wait and retry
    below is a configured value rather than a literal.
    """

    # Narrows what `ParsingSession` stores: the resolved config is carwow's.
    _config: CarWowConfig

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
                for i in range(self._config.result_sync_retries):
                    try:
                        # if false waits until timeout and throws
                        self._page.wait_for_function(
                            expression=js_frame_load_checker,
                            arg=frame_id,
                            timeout=self._config.result_sync_timeout_ms)
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
                wait_seconds = self._config.new_page_load_wait_seconds
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
            for i in range(self._config.max_next_pagination_batch_retries):
                if self.step_to_next_pagination_batch(pagination_index, pagination_list_locator):
                    break
                else:
                    logger.error("Unable to move to next pagination batch %s, retrying... (%s)", pagination_index+1, i)
                    sleep(self._config.pagination_retry_sleep_seconds)

        # TODO: putting this here for now:
        # select price, make, model, mileage, year, engine_size, url from raw_used_car_listing where transmission = 'Automatic' order by price;
        # select count(id) from raw_used_car_listing where transmission = 'Automatic'
