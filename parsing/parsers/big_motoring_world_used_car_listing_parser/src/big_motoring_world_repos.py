import logging

from pydantic import Field
from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from base_used_car_listing_parser import (
    BaseRawUsedCarListing,
    BaseRawUsedCarListingORM,
    BaseRawUsedCarListingSqlAlchemyRepository,
    Source,
)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)


class BigMotoringWorldRawUsedCarListing(BaseRawUsedCarListing):
    match_score: str = Field(default="poor", description="The BigMotoringWorld score on how well the job matches the profile")


class BigMotoringWorldRawUsedCarListingORM(BaseRawUsedCarListingORM):
    """Joined-table ORM for BigMotoringWorld listings; FK back to ``raw_used_car_listing.id``."""

    __tablename__ = "big_motoring_world_raw_used_car_listing"

    id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("raw_used_car_listing.id", ondelete="CASCADE"),
        primary_key=True,
    )
    match_score: Mapped[str] = mapped_column(String, nullable=False, default="poor")

    __mapper_args__ = {"polymorphic_identity": Source.BIG_MOTORING_WORLD}


class BigMotoringWorldRawUsedCarListingSqlAlchemyRepository(BaseRawUsedCarListingSqlAlchemyRepository):
    # The base repo's add/get already operate on the concrete ORM/PYDANTIC via
    # joined-table inheritance, so no overrides are needed here.
    ORM = BigMotoringWorldRawUsedCarListingORM
    PYDANTIC = BigMotoringWorldRawUsedCarListing
