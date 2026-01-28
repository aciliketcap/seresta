import logging

from pydantic import Field
from sqlalchemy import ForeignKey, String, select
from sqlalchemy.orm import Mapped, mapped_column

from base_job_postings_parser import (
    BaseRawJobPosting,
    BaseRawJobPostingORM,
    BaseRawJobPostingSqlAlchemyRepository,
)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)

LINKEDIN_SOURCE = "linkedin"


class LinkedInRawJobPosting(BaseRawJobPosting):
    match_score: str = Field(default="poor", description="The LinkedIn score on how well the job matches the profile")


class LinkedInRawJobPostingORM(BaseRawJobPostingORM):
    """Joined-table ORM for LinkedIn job postings; FK back to ``raw_job_posting.id``."""

    __tablename__ = "linkedin_raw_job_posting"

    id: Mapped[str] = mapped_column(
        String,
        ForeignKey("raw_job_posting.id", ondelete="CASCADE"),
        primary_key=True,
    )
    match_score: Mapped[str] = mapped_column(String, nullable=False, default="poor")

    __mapper_args__ = {"polymorphic_identity": LINKEDIN_SOURCE}


class LinkedInRawJobPostingSqlAlchemyRepository(BaseRawJobPostingSqlAlchemyRepository):
    ORM = LinkedInRawJobPostingORM
    PYDANTIC = LinkedInRawJobPosting

    def add(self, job_posting: LinkedInRawJobPosting) -> None:
        super().add(job_posting)
        with self._sm.begin() as session:
            session.merge(self.ORM(**job_posting.model_dump(mode="json")))

    def get(self, job_posting_id: str) -> LinkedInRawJobPosting | None:
        with self._sm() as session:
            # Polymorphism returns the concrete ORM subclass; model_validate
            # then yields the matching Pydantic subclass.
            row = session.get(self.ORM, job_posting_id)
            return self.PYDANTIC.model_validate(row) if row is not None else None  # type: ignore[return-value]

    def find_all_by_processed(self, processed: bool) -> list[LinkedInRawJobPosting]:
        with self._sm() as session:
            rows = session.scalars(
                select(self.ORM).where(self.ORM.processed == processed)
            ).all()
            return [self.PYDANTIC.model_validate(r) for r in rows]  # type: ignore[misc]
        
