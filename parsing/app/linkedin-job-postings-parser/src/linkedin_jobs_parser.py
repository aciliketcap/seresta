from typing import Any, Generator
from playwright.sync_api import Locator, Page
from serespar import ResultsParseSession
import logging
from time import sleep # for sleeping random amounts of time between clicks

logger = logging.getLogger(__name__)

LINKEDIN_SEARCH_SELECTORS = {
    "JOB_BUTTON_LIST": 'div[role="button"].a0d6ff3a._19cba76e._94ed88e7.b89d528a._36cb9d95.c926a983._91053ffa._3500e8e0.f2644b16.dd8fcdd5.d390f4b8.f2e39baa._20be700a',
    "PAGINATION_LIST": 'css=ul.jobs-search-pagination__pages > li > button'
}
NEXT_CARD_LOAD_WAIT_SECONDS=1
NEW_PAGE_LOAD_WAIT_SECONDS=3

JOB_BUTTON_SCROLL_PIXELS = 120

class LinkedInJobsParseSession(ResultsParseSession):
    def results_in_pagination(self) -> Generator[tuple[Page, Locator], Any, Any]:
        job_button_list_locator = self._page.locator(LINKEDIN_SEARCH_SELECTORS["JOB_BUTTON_LIST"])
        for job_button in job_button_list_locator.all():
            job_button.scroll_into_view_if_needed()
            job_button.click()
            # TODO: check that card is loaded with an overloadable library function in serespar side, only use magic sleep if that's too much work
            sleep(NEXT_CARD_LOAD_WAIT_SECONDS)
            yield self._page, job_button
            logger.debug("move mouse wheel down a little")
            self._page.mouse.wheel(0,JOB_BUTTON_SCROLL_PIXELS)
            sleep(1)
            logger.debug("moving on to the next card")

    def paginations_in_search_results(self, max_pagination: int) -> Generator[int, Any, None]:
        for cur_page_num in range(1, max_pagination):

            yield cur_page_num

            pagi_list_locator = self._page.locator(LINKEDIN_SEARCH_SELECTORS["PAGINATION_LIST"])
            for pagi in pagi_list_locator.all():
                pagi_text = pagi.locator("css=span").text_content()
                logger.debug(f"pagination number is {pagi_text}")
                # bug in LinkedIn causes … to show instead of 9 when on 8th page
                if cur_page_num == 9:
                    if pagi_text == '…':
                        pagi.click()
                        break
                else:
                    if pagi_text == str(cur_page_num + 1):
                        pagi.click()
                        break
            self._page.wait_for_load_state()
            logger.debug(f"moved to page {cur_page_num + 1}, sleeping {NEW_PAGE_LOAD_WAIT_SECONDS}")
            sleep(NEW_PAGE_LOAD_WAIT_SECONDS)
