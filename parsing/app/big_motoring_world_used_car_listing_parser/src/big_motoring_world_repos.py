import logging

from pydantic import Field
from sqlalchemy import ForeignKey, String, select
from sqlalchemy.orm import Mapped, mapped_column

from base_used_car_listing_parser import (
    BaseRawUsedCarListing,
    BaseRawUsedCarListingORM,
    BaseRawUsedCarListingSqlAlchemyRepository,
)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)

LINKEDIN_SOURCE = "big_motoring_world"


class BigMotoringWorldRawUsedCarListing(BaseRawUsedCarListing):
    match_score: str = Field(default="poor", description="The BigMotoringWorld score on how well the job matches the profile")


class BigMotoringWorldRawUsedCarListingORM(BaseRawUsedCarListingORM):
    """Joined-table ORM for BigMotoringWorld job postings; FK back to ``raw_used_car_listing.id``."""

    __tablename__ = "big_motoring_world_raw_used_car_listing"

    id: Mapped[str] = mapped_column(
        String,
        ForeignKey("raw_used_car_listing.id", ondelete="CASCADE"),
        primary_key=True,
    )
    match_score: Mapped[str] = mapped_column(String, nullable=False, default="poor")

    __mapper_args__ = {"polymorphic_identity": LINKEDIN_SOURCE}


class BigMotoringWorldRawUsedCarListingSqlAlchemyRepository(BaseRawUsedCarListingSqlAlchemyRepository):
    ORM = BigMotoringWorldRawUsedCarListingORM
    PYDANTIC = BigMotoringWorldRawUsedCarListing

    def add(self, used_car_listing: BigMotoringWorldRawUsedCarListing) -> None:
        super().add(used_car_listing)
        with self._sm.begin() as session:
            session.merge(self.ORM(**used_car_listing.model_dump(mode="json")))

    def get(self, used_car_listing_id: str) -> BigMotoringWorldRawUsedCarListing | None:
        with self._sm() as session:
            # Polymorphism returns the concrete ORM subclass; model_validate
            # then yields the matching Pydantic subclass.
            row = session.get(self.ORM, used_car_listing_id)
            return self.PYDANTIC.model_validate(row) if row is not None else None  # type: ignore[return-value]
        
