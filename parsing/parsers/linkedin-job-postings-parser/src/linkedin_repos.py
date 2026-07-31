import logging

from pydantic import Field
from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from base_job_postings_parser import (
    BaseRawJobPosting,
    BaseRawJobPostingORM,
    BaseRawJobPostingSqlAlchemyRepository,
    Source,
)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)


class LinkedInRawJobPosting(BaseRawJobPosting):
    match_score: str = Field(default="poor", description="The LinkedIn score on how well the job matches the profile")


class LinkedInRawJobPostingORM(BaseRawJobPostingORM):
    """Joined-table ORM for LinkedIn job postings; FK back to ``raw_job_posting.id``."""

    __tablename__ = "linkedin_raw_job_posting"

    id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("raw_job_posting.id", ondelete="CASCADE"),
        primary_key=True,
    )
    match_score: Mapped[str] = mapped_column(String, nullable=False, default="poor")

    __mapper_args__ = {"polymorphic_identity": Source.LINKEDIN}


class LinkedInRawJobPostingSqlAlchemyRepository(BaseRawJobPostingSqlAlchemyRepository):
    # The base repo's add/get/find_all_by_processed already operate on the
    # concrete ORM/PYDANTIC via joined-table inheritance, so no overrides needed.
    ORM = LinkedInRawJobPostingORM
    PYDANTIC = LinkedInRawJobPosting
