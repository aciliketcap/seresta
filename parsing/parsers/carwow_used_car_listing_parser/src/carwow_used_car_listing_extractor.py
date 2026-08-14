import dataclasses
import logging

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
    "SUMMARY_ELTS": "div.deal-card__details ul li",
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
    def _extract_id_url(self) -> tuple[str, Url]:
        url = self.url_from_link_elt(self._result_locator.locator(CARWOW_CAR_CARD_SELECTORS["URL"]))
        id = str(url).split("/")[-1]
        return id, url

    @BaseExtractor.critical_info
    def _extract_make_model(self) -> tuple[str, str]:
        make_model_str: str = self.text_at_selector(CARWOW_CAR_CARD_SELECTORS["MAKE_MODEL"])
        make_model = make_model_str.split(maxsplit=1)
        return make_model[0].strip(), make_model[1].strip()

    @BaseExtractor.critical_info
    def _extract_location_year_miles(self) -> tuple[str|None, int, int]:
        details = self._result_locator.locator(CARWOW_CAR_CARD_SELECTORS["DETAILS"]).first
        details_elts = details.locator("ul > li").all()
        location = None
        if len(details_elts) == 3:
            # location, year, miles instead of year, miles
            location= self.text_at_locator(details_elts[0])
            details_elts.pop(0)

        year = int(self.text_at_locator(details_elts[0]))
        miles_str = self.text_at_locator(details_elts[1]).split(" ", maxsplit=1)[0].replace(",","")
        miles = int(miles_str)
        return location, year, miles
    
    @BaseExtractor.critical_info
    def _extract_price(self) -> int:
        full_price_str: str = self.text_at_selector(CARWOW_CAR_CARD_SELECTORS["PRICE"])
        return int(full_price_str[1:].replace(",", ""))

    @BaseExtractor.critical_info
    def _extract_summary_elts(self) -> SummarySection:
        summary_elt_locs = self._result_locator.locator(CARWOW_CAR_CARD_SELECTORS["SUMMARY_ELTS"]).all()
        transmission: str = self.text_at_locator(summary_elt_locs[0])
        fuel_type: str = self.text_at_locator(summary_elt_locs[1])
        if fuel_type == "Electric":
            engine_size = None
        else:
            engine_size_str: str = self.text_at_locator(summary_elt_locs[2])
            engine_size: int = int(engine_size_str[:-2].replace(".", ""))
        return SummarySection(
            transmission=transmission,
            fuel_type=fuel_type,
            engine_size=engine_size,
        )

    @BaseExtractor.critical_info
    def _extract_trim(self) -> str:
        return self.text_at_selector(CARWOW_CAR_CARD_SELECTORS["TRIM"])

    def extract_and_persist(self) -> None:
        trim = self._extract_trim()
        make, model = self._extract_make_model()
        result_id, url = self._extract_id_url()
        price = self._extract_price()
        summary_section: SummarySection = self._extract_summary_elts()
        location, year, miles = self._extract_location_year_miles()

        self._parsed_entity = CarWowRawUsedCarListing(
            source=Source.CARWOW,
            result_id=result_id,
            last_found_in=self._tracker.parsing_session_id,
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
            location=location,
        )
