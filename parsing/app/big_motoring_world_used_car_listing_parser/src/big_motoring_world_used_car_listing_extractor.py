import dataclasses
import logging
import re

from playwright.sync_api import Locator, Page
from pydantic_core import Url

from base_used_car_listing_parser import UsedCarListingExtractor, UsedCarListingExtractionError
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

class BigMotoringWorldUsedCarListingExtractor(UsedCarListingExtractor):
    def __init__(self, repo: BigMotoringWorldRawUsedCarListingSqlAlchemyRepository):
        super().__init__(repo)

    # TODO: make _extract_??? methods fail gracefully

    def _extract_id_url(self, item: Locator) -> tuple[str, Url]:
        url: str = BMW_BASE_URL + item.get_attribute("href")
        id = url.split("-")[-1][:-1]
        return id, Url(url)

    def _extract_make_model(self, item: Locator) -> tuple[str, str]:
        make_model_str: str = item.locator(BMW_CAR_CARD_SELECTORS["MAKE_MODEL"]).text_content()
        make_model = make_model_str.split(maxsplit=1)
        return make_model[0], make_model[1]

    def _extract_year_trim(self, item: Locator) -> tuple[int, str]:
        year_trim_str: str = item.locator(BMW_CAR_CARD_SELECTORS["SPEC"]).text_content()
        year_trim = year_trim_str.split("|", maxsplit=1)
        return int(year_trim[0].strip()), year_trim[1].strip()
    
    def _extract_price(self, item: Locator) -> int:
        full_price_str: str = item.locator(selector_or_locator=BMW_CAR_CARD_SELECTORS["PRICE"]).first.text_content()
        return int(full_price_str[1:].replace(",", ""))

    def _extract_miles(self, miles_info: Locator) -> int:
        miles_str = miles_info.text_content()
        return int(miles_str.split(" ")[0].replace(",", ""))

    def _extract_infos(self, item: Locator) -> CarInfos:
        info_locators = item.locator(BMW_CAR_CARD_SELECTORS["INFO_FLEX_ELTS"]).all()
        miles = self._extract_miles(info_locators[0])
        transmission: str = info_locators[1].text_content()
        fuel_type: str = info_locators[2].text_content()
        if fuel_type == "Electric":
            engine_size = None
            range_str: str = info_locators[3].text_content()
            range = int(range_str.split(" ", maxsplit=1)[0])
        else:
            engine_size_str: str = info_locators[3].text_content()
            engine_size: int = int(engine_size_str[:-1].replace(".", ""))
            range = None
        return CarInfos(
            miles=miles,
            transmission=transmission,
            fuel_type=fuel_type,
            engine_size=engine_size,
            range=range,
        )

    def _extract_location(self, item: Locator) -> str:
        location_str: str = item.locator(BMW_CAR_CARD_SELECTORS["LOCATION"]).text_content()
        return location_str.strip()


    def extract_and_persist(self, page: Page, item: Locator) -> None:
        try:
            make, model = self._extract_make_model(item)
            id, url = self._extract_id_url(item)
            price = self._extract_price(item)
            car_infos: CarInfos = self._extract_infos(item)
            year, trim = self._extract_year_trim(item)
            location = self._extract_location(item)

            used_car_listing = BigMotoringWorldRawUsedCarListing(
                id="big_motoring_world_" + id,
                source="big_motoring_world",
                source_id=id,
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

        except: # TODO: I'm not sure what I'm catching for, need to do some trial and error
            raise UsedCarListingExtractionError("we will raise like this if we can't parse a card!")

        self._repo.add(used_car_listing)
