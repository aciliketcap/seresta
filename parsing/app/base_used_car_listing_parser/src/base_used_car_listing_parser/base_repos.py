"""A model of the info in the job cards. Called raw because the JD is not processed yet."""

import abc

from pydantic import BaseModel, ConfigDict, Field
from pydantic_core import Url
from sqlalchemy import Boolean, String, Integer, select
from sqlalchemy.orm import Mapped, Session, mapped_column, sessionmaker

from .db import Base


class BaseRawUsedCarListing(BaseModel):
    """A used car listing as it was initially extracted (therefore raw)"""
    model_config = ConfigDict(from_attributes=True)

    id: str
    # TODO: make this an enum with values like "BigMotoringWorld", "CarGiant" etc
    source: str = Field(description="The used car listing website")
    source_id: str = Field(description="The unique id of the used car listing  in the used car website")
    url: Url = Field(description="The URL of the used car listing")
    make: str = Field(description="The make of the used car")
    model: str = Field(description="The model of the used car")
    trim: str = Field(description="The trim of the used car")
    year: int = Field(description="The year of the used car")
    price: int = Field(description="The price of the used car")
    mileage: int = Field(description="The mileage of the used car")
    fuel_type: str = Field(description="The fuel type of the used car (petrol, diesel, hybrid, electric)")
    transmission: str = Field(description="The transmission of the used car (manual, automatic, CVT, etc.)")
    engine_size: int|None = Field(description="The engine size of the used car (petrol, diesel, hybrid)")
    range: int|None = Field(description="The range of the used car (electric)")
    location: str|None = Field(description="The location of the used car")

class BaseRawUsedCarListingORM(Base):
    """SQLAlchemy ORM mapping for ``BaseRawUsedCarListing`` (joined-table inheritance root)."""

    __tablename__ = "raw_used_car_listing"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    source: Mapped[str] = mapped_column(String, nullable=False)
    source_id: Mapped[str] = mapped_column(String, nullable=False)
    url: Mapped[str] = mapped_column(String, nullable=False)
    make: Mapped[str] = mapped_column(String, nullable=False)
    model: Mapped[str] = mapped_column(String, nullable=False)
    trim: Mapped[str] = mapped_column(String, nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[int] = mapped_column(Integer, nullable=False)
    mileage: Mapped[int] = mapped_column(Integer, nullable=False)
    fuel_type: Mapped[str] = mapped_column(String, nullable=False)
    transmission: Mapped[str] = mapped_column(String, nullable=False)
    engine_size: Mapped[int|None] = mapped_column(Integer, nullable=True)
    range: Mapped[int|None] = mapped_column(Integer, nullable=True)
    location: Mapped[str|None] = mapped_column(String, nullable=True)

    __mapper_args__ = {
        "polymorphic_on": "source",
        # Sentinel identity for plain (non-subclassed) BaseRawUsedCarListing rows.
        # Real sources ("linkedin", "indeed", ...) override this on the ORM subclass.
        "polymorphic_identity": "raw",
    }

class AbstractBaseRawUsedCarListingRepository(abc.ABC):
    @abc.abstractmethod
    def add(self, used_car_listing: BaseRawUsedCarListing) -> None:
        pass

    @abc.abstractmethod
    def get(self, used_car_listing_id: str) -> BaseRawUsedCarListing | None:
        pass


# Setting it into stone that an sqlalchemy repo will exist eventually is for convenience. But it is also unnecessary rigidity, bringing in sqlalchemy dependency to all sub-projects.
class BaseRawUsedCarListingSqlAlchemyRepository(AbstractBaseRawUsedCarListingRepository):
    # Subclasses override these with their concrete ORM + Pydantic classes.
    ORM: type[BaseRawUsedCarListingORM] = BaseRawUsedCarListingORM
    PYDANTIC: type[BaseRawUsedCarListing] = BaseRawUsedCarListing

    def __init__(self, sm: sessionmaker[Session]) -> None:
        self._sm = sm

    def add(self, used_car_listing: BaseRawUsedCarListing) -> None:
        # mode="json" so pydantic_core.Url becomes str for the String column.
        with self._sm.begin() as session:
            # merge() makes adding the same used car listing idempotent on `id`.
            session.merge(self.ORM(**used_car_listing.model_dump(mode="json")))

    def get(self, used_car_listing_id: str) -> BaseRawUsedCarListing | None:
        with self._sm() as session:
            # Polymorphism returns the concrete ORM subclass; model_validate
            # then yields the matching Pydantic subclass.
            row = session.get(self.ORM, used_car_listing_id)
            return self.PYDANTIC.model_validate(row) if row is not None else None  # type: ignore[return-value]

