"""A model of the info in the job cards. Called raw because the JD is not processed yet."""

import abc

from pydantic import BaseModel, ConfigDict, Field
from pydantic_core import Url
from sqlalchemy import Boolean, String, select
from sqlalchemy.orm import Mapped, Session, mapped_column, sessionmaker

from .db import Base


class BaseRawJobPosting(BaseModel):
    """A job posting on job search websiteas it was initially extracted (therefore raw)"""
    model_config = ConfigDict(from_attributes=True)

    id: str
    # TODO: make this an enum with values like "LinkedIn", "Indeed" etc
    source: str = Field(description="The job search website this job posting was read")
    source_id: str = Field(description="The unique id of the job posting in the job search website")
    url: Url = Field(description="The URL of the job posting")
    title: str = Field(description="The title of the job posting")
    jd_text: str = Field(description="The job description as text")
    jd_html: str = Field(description="The job description as HTML")
    processed: bool = Field(default=False, description="Whether the raw job posting was processed before")


class BaseRawJobPostingORM(Base):
    """SQLAlchemy ORM mapping for ``BaseRawJobPosting`` (joined-table inheritance root)."""

    __tablename__ = "raw_job_posting"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    source: Mapped[str] = mapped_column(String, nullable=False)
    source_id: Mapped[str] = mapped_column(String, nullable=False)
    url: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    jd_text: Mapped[str] = mapped_column(String, nullable=False)
    jd_html: Mapped[str] = mapped_column(String, nullable=False)
    processed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __mapper_args__ = {
        "polymorphic_on": "source",
        # Sentinel identity for plain (non-subclassed) BaseRawJobPosting rows.
        # Real sources ("linkedin", "indeed", ...) override this on the ORM subclass.
        "polymorphic_identity": "raw",
    }

class AbstractBaseRawJobPostingRepository(abc.ABC):
    @abc.abstractmethod
    def add(self, job_posting: BaseRawJobPosting) -> None:
        pass

    @abc.abstractmethod
    def get(self, job_posting_id: str) -> BaseRawJobPosting | None:
        pass

    @abc.abstractmethod
    def find_all_by_processed(self, processed: bool) -> list[BaseRawJobPosting]:
        pass

# Setting it into stone that an sqlalchemy repo will exist eventually is for convenience. But it is also unnecessary rigidity, bringing in sqlalchemy dependency to all sub-projects.
class BaseRawJobPostingSqlAlchemyRepository(AbstractBaseRawJobPostingRepository):
    # Subclasses override these with their concrete ORM + Pydantic classes.
    ORM: type[BaseRawJobPostingORM] = BaseRawJobPostingORM
    PYDANTIC: type[BaseRawJobPosting] = BaseRawJobPosting

    def __init__(self, sm: sessionmaker[Session]) -> None:
        self._sm = sm

    def add(self, job_posting: BaseRawJobPosting) -> None:
        # mode="json" so pydantic_core.Url becomes str for the String column.
        with self._sm.begin() as session:
            # merge() makes adding the same job posting idempotent on `id`.
            session.merge(self.ORM(**job_posting.model_dump(mode="json")))

    def get(self, job_posting_id: str) -> BaseRawJobPosting | None:
        with self._sm() as session:
            # Polymorphism returns the concrete ORM subclass; model_validate
            # then yields the matching Pydantic subclass.
            row = session.get(self.ORM, job_posting_id)
            return self.PYDANTIC.model_validate(row) if row is not None else None  # type: ignore[return-value]

    def find_all_by_processed(self, processed: bool) -> list[BaseRawJobPosting]:
        with self._sm() as session:
            rows = session.scalars(
                select(self.ORM).where(self.ORM.processed == processed)
            ).all()
            return [self.PYDANTIC.model_validate(r) for r in rows]  # type: ignore[misc]
