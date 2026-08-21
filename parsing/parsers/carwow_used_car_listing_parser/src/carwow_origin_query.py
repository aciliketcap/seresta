"""carwow's `OriginQueryProcess`: the search is typed into the filter widgets.

carwow does not put its filters in the URL, so opening the `OriginUrl` is only
the first step: the postcode, the price range, the age range, the fuel types
and the gearbox all have to be set on the page before the results are the ones
this task asked for.

That is a property of carwow, not of parsing in general, which is why it is a
strategy the builder injects into the session rather than an override of it.
The session that walks the results does not know any of this happened.
"""

import logging
from time import sleep

from playwright.sync_api import Page

from .config import CarWowOriginQuery

logger = logging.getLogger(__name__)

CARWOW_FILTER_SELECTORS = {
    "LOCATION_INPUT": "input#location-desktop",
    "PRICE_FROM": "select#price-gte-desktop",
    "PRICE_TO": "select#price-lte-desktop",
    "AGE": "li#age-desktop",
    "AGE_FROM": "select#age-gte-desktop",
    "AGE_TO": "select#age-lte-desktop",
    "FUEL_TYPE": "li#fuel_type-desktop",
    "GEARBOX": "li#gearbox-desktop",
}


class CarWowFilterFormsQueryProcess:
    """Opens the `OriginUrl` and fills carwow's filters in with the `OriginQuery`.

    ``settle_seconds`` is the `DelayBehavior` between interactions: the page
    re-renders after each filter, and the next widget is only there once it
    has.
    """

    def __init__(
        self,
        origin_url: str,
        origin_query: CarWowOriginQuery,
        settle_seconds: float,
    ) -> None:
        self._origin_url = origin_url
        self._origin_query = origin_query
        self._settle_seconds = settle_seconds

    def open_results(self, page: Page) -> None:
        page.goto(self._origin_url, wait_until="load")
        logger.info("URL `%s` should be loaded now.", self._origin_url)

        self._set_location(page)
        self._set_price(page)
        self._set_age(page)
        self._set_fuel_types(page)
        self._set_transmission(page)

        logger.info("Initiated the search.")

    # -- one filter at a time ---------------------------------------------

    def _settle(self) -> None:
        sleep(self._settle_seconds)

    def _set_location(self, page: Page) -> None:
        # TODO: these input elts are also lazily loaded
        page.locator(CARWOW_FILTER_SELECTORS["LOCATION_INPUT"]).fill(
            self._origin_query.postcode
        )
        self._settle()
        page.get_by_text("Set location").click()
        self._settle()
        logger.info("location set")

    def _set_price(self, page: Page) -> None:
        page.locator(CARWOW_FILTER_SELECTORS["PRICE_FROM"]).select_option(
            str(self._origin_query.price_min)
        )
        self._settle()
        page.locator(CARWOW_FILTER_SELECTORS["PRICE_TO"]).select_option(
            str(self._origin_query.price_max)
        )
        self._settle()
        logger.info(
            "price set to %s - %s",
            self._origin_query.price_min,
            self._origin_query.price_max,
        )

    def _set_age(self, page: Page) -> None:
        age_loc = page.locator(CARWOW_FILTER_SELECTORS["AGE"])
        age_loc.click()

        age_from_opts = age_loc.locator(
            f'{CARWOW_FILTER_SELECTORS["AGE_FROM"]} option'
        ).all()
        # TODO: make this base method, also what if value is not in any of the options?
        age_from_opt_value = [
            opt.get_attribute("value")
            for opt in age_from_opts
            if f"{self._origin_query.age_from} " in opt.text_content().strip()
        ][0]
        age_loc.locator(CARWOW_FILTER_SELECTORS["AGE_FROM"]).select_option(
            age_from_opt_value
        )
        self._settle()
        logger.info("age from set to %s", self._origin_query.age_from)

        age_to_opts = age_loc.locator(
            f'{CARWOW_FILTER_SELECTORS["AGE_TO"]} option'
        ).all()
        age_to_opt_value = [
            opt.get_attribute("value")
            for opt in age_to_opts
            if f"{self._origin_query.age_to} " in opt.text_content().strip()
        ][0]
        age_loc.locator(CARWOW_FILTER_SELECTORS["AGE_TO"]).select_option(
            age_to_opt_value
        )
        self._settle()
        logger.info("age to set to %s", self._origin_query.age_to)

    def _set_fuel_types(self, page: Page) -> None:
        page.locator(CARWOW_FILTER_SELECTORS["FUEL_TYPE"]).click()
        for fuel_type in self._origin_query.fuel_types:
            page.get_by_label(fuel_type).first.click()
            self._settle()
        logger.info("fuel to set to %s", self._origin_query.fuel_types)

    def _set_transmission(self, page: Page) -> None:
        gearbox = page.locator(CARWOW_FILTER_SELECTORS["GEARBOX"])
        gearbox.click()
        gearbox.get_by_text(self._origin_query.transmission).first.click()
        logger.info("transmission to set to %s", self._origin_query.transmission)
