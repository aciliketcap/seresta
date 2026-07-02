import dataclasses
import logging
import re

from playwright.sync_api import Locator, Page
from pydantic_core import Url

from base_used_car_listing_parser.base_repos import Source
from serespar import BaseExtractor
from .carwow_repos import CarWowRawUsedCarListing, CarWowRawUsedCarListingSqlAlchemyRepository


logger = logging.getLogger(__name__)

CARWOW_CAR_CARD_SELECTORS = {
    "TRIM": "div.deal-card__derivative",
    "URL": "a.deal-card__link",
    "MAKE_MODEL": "div.deal-card__title",
    "PRICE": "div.deal-card__price",
    "SUMMARY_ELTS": "div.deal-card__summary ul li",
    "DETAILS": "div.deal-card__section--anchor-bottom"
}

@dataclasses.dataclass
class SummarySection():
    transmission: str
    fuel_type: str
    engine_size: int|None = None

class CarWowUsedCarListingExtractor(BaseExtractor[
        CarWowRawUsedCarListingSqlAlchemyRepository,
        CarWowRawUsedCarListing
        ]):

    @BaseExtractor.critical_info
    def _extract_id_url(self, item: Locator) -> tuple[str, Url]:
        url: str = item.locator(CARWOW_CAR_CARD_SELECTORS["URL"]).get_attribute("href")
        id = url.split("/")[-1]
        return id, Url(url)

    @BaseExtractor.critical_info
    def _extract_make_model(self, item: Locator) -> tuple[str, str]:
        make_model_str: str = item.locator(CARWOW_CAR_CARD_SELECTORS["MAKE_MODEL"]).text_content()
        make_model = make_model_str.split(maxsplit=1)
        return make_model[0].strip(), make_model[1].strip()

    @BaseExtractor.critical_info
    def _extract_year_miles(self, item: Locator) -> tuple[int, int]:
        details: str = item.locator(CARWOW_CAR_CARD_SELECTORS["DETAILS"]).first
        details_elts = details.locator("ul > li").all()
        year_str = details_elts[0].text_content().strip()
        year = int(year_str)
        miles_str = details_elts[1].text_content().strip().split(" ", maxsplit=1)[0].replace(",","")
        miles = int(miles_str)
        return year, miles
    
    @BaseExtractor.critical_info
    def _extract_price(self, item: Locator) -> int:
        full_price_str: str = item.locator(selector_or_locator=CARWOW_CAR_CARD_SELECTORS["PRICE"]).first.text_content().strip()
        return int(full_price_str[1:].replace(",", ""))

    @BaseExtractor.critical_info
    def _extract_summary_elts(self, item: Locator) -> SummarySection:
        summary_elt_locs = item.locator(CARWOW_CAR_CARD_SELECTORS["SUMMARY_ELTS"]).all()
        transmission: str = summary_elt_locs[0].text_content()
        fuel_type: str = summary_elt_locs[1].text_content()
        if fuel_type == "Electric":
            engine_size = None
        else:
            engine_size_str: str = summary_elt_locs[2].text_content()
            engine_size: int = int(engine_size_str[:-2].replace(".", ""))
        return SummarySection(
            transmission=transmission,
            fuel_type=fuel_type,
            engine_size=engine_size,
        )

    def extract_and_persist(self) -> None:
        trim = item.locator(CARWOW_CAR_CARD_SELECTORS["TRIM"]).text_content().strip()
        make, model = self._extract_make_model(item)
        seres_id, url = self._extract_id_url(item)
        price = self._extract_price(item)
        summary_section: SummarySection = self._extract_summary_elts(item)
        year, miles = self._extract_year_miles(item)

        self._seres = CarWowRawUsedCarListing(
            source=Source.CARWOW,
            seres_id=seres_id,
            last_found_in=parse_session_id,
            url=url,
            trim=trim,
            make=make,
            model=model,
            year=year,
            price=price,
            mileage=miles,
            fuel_type=summary_section.fuel_type,
            transmission=summary_section.transmission,
            engine_size=summary_section.engine_size,
            range=None,
            location=None,
        )

off cursor tab ile yapalim yarin sabah abi