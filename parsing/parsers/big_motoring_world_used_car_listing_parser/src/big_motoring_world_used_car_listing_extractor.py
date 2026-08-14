from base_used_car_listing_parser.base_repos import Source
from serespar import BaseExtractor
import dataclasses
import logging

from playwright.sync_api import Locator, Page
from pydantic_core import Url

from .big_motoring_world_repos import BigMotoringWorldRawUsedCarListing, BigMotoringWorldRawUsedCarListingSqlAlchemyRepository

logger = logging.getLogger(__name__)
BMW_BASE_URL = "https://www.bigmotoringworld.co.uk"
BMW_CAR_CARD_SELECTORS = {
    "MAKE_MODEL": "div.card-body div.make",
    "SPEC": "div.card-body div.spec",
    "PRICE": "div.full-price", # TODO: I can't define this selector precisely, why?
    "INFO_FLEX_ELTS": "div.card-body div.info-section div.info",
    "LOCATION": "div.card-body div.location-wrapper"
}

@dataclasses.dataclass
class CarInfos():
    miles: int
    transmission: str
    fuel_type: str
    engine_size: int|None = None
    range: int|None = None

class BigMotoringWorldUsedCarListingExtractor(
    BaseExtractor[
        BigMotoringWorldRawUsedCarListingSqlAlchemyRepository,
        BigMotoringWorldRawUsedCarListing
        ]):
    @BaseExtractor.critical_info
    def _extract_id_url(self) -> tuple[str, Url]:
        url = self.url_from_link_elt(self._result_locator.get_attribute("href"), BMW_BASE_URL)
        id = str(url).split("-")[-1][:-1]
        return id, url

    @BaseExtractor.critical_info
    def _extract_make_model(self) -> tuple[str, str]:
        make_model_str: str = self.text_at_selector(BMW_CAR_CARD_SELECTORS["MAKE_MODEL"])
        make_model = make_model_str.split(maxsplit=1)
        return make_model[0], make_model[1]

    @BaseExtractor.critical_info
    def _extract_year_trim(self) -> tuple[int, str]:
        year_trim_str: str = self.text_at_selector(BMW_CAR_CARD_SELECTORS["SPEC"])
        year_trim = year_trim_str.split("|", maxsplit=1)
        return int(year_trim[0].strip()), year_trim[1].strip()
    
    @BaseExtractor.critical_info
    def _extract_price(self) -> int:
        full_price_str: str = self.text_at_selector(BMW_CAR_CARD_SELECTORS["PRICE"])
        return int(full_price_str[1:].replace(",", ""))

    @BaseExtractor.critical_info
    def _extract_miles(self, miles_loc) -> int:
        miles_str = self.text_at_locator(miles_loc)
        return int(miles_str.split(" ")[0].replace(",", ""))

    @BaseExtractor.critical_info
    def _extract_infos(self) -> CarInfos:
        info_locators = self._result_locator.locator(BMW_CAR_CARD_SELECTORS["INFO_FLEX_ELTS"]).all()
        miles = self._extract_miles(info_locators[0])
        transmission: str = self.text_at_locator(info_locators[1])
        fuel_type: str = self.text_at_locator(info_locators[2])
        if fuel_type == "Electric":
            engine_size = None
            range_str: str = self.text_at_locator(info_locators[3])
            range = int(range_str.split(" ", maxsplit=1)[0])
        else:
            engine_size_str: str = self.text_at_locator(info_locators[3])
            engine_size: int = int(engine_size_str[:-1].replace(".", ""))
            range = None
        return CarInfos(
            miles=miles,
            transmission=transmission,
            fuel_type=fuel_type,
            engine_size=engine_size,
            range=range,
        )

    @BaseExtractor.noncrit_info(error_value=None)
    def _extract_location(self) -> str:
        location_str: str = self.text_at_selector(BMW_CAR_CARD_SELECTORS["LOCATION"])
        return location_str.strip()

    def extract_and_persist(self) -> None:
        make, model = self._extract_make_model()
        result_id, url = self._extract_id_url()
        price = self._extract_price()
        car_infos: CarInfos = self._extract_infos()
        year, trim = self._extract_year_trim()
        location = self._extract_location()

        self._parsed_entity = BigMotoringWorldRawUsedCarListing(
            source=Source.BIG_MOTORING_WORLD,
            result_id=result_id,
            last_found_in=self._tracker.parsing_session_id,
            url=url,
            trim=trim,
            make=make,
            model=model,
            year=year,
            price=price,
            mileage=car_infos.miles,
            fuel_type=car_infos.fuel_type,
            transmission=car_infos.transmission,
            engine_size=car_infos.engine_size,
            range=car_infos.range,
            location=location,
        )
