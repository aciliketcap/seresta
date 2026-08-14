import logging
import re

from playwright.sync_api import Locator, Page
from pydantic_core import Url

from base_job_postings_parser import JobPostingExtractor, JobPostingExtractionError, Source
from .linkedin_repos import LinkedInRawJobPosting, LinkedInRawJobPostingSqlAlchemyRepository


logger = logging.getLogger(__name__)

LINKEDIN_JOB_POSTING_SELECTORS = {
    "JOB_POSTING_FRAME": 'div._405e5d1a._29598395._35cebee5.a554aeef',
    "TITLE_AND_URL": 'a.d390f4b8._95b5a644',
    "JD": 'p._9e348bbd._51112094._33a19d00.e17582ce.eed62b1d._684e3d2d._5ed4d071.cb8df2cc._4fb23d32._98fdec3a._7386006e'
}

ID_EXTRACTOR_RE_STR = r"^https://www.linkedin.com/jobs/view/([0-9]+)/.*"

class LinkedInJobPostingExtractor(JobPostingExtractor):
    def __init__(self, repo: LinkedInRawJobPostingSqlAlchemyRepository):
        super().__init__(repo)

    def extract_and_persist(self, page: Page, job_card: Locator, parsing_session_id: int) -> None:
        try:
            # we don't use dynamic job_card, we go to the same div which holds the whole job posting
            jp_frame = page.locator(LINKEDIN_JOB_POSTING_SELECTORS["JOB_POSTING_FRAME"])
            title_and_url_loc = jp_frame.locator(LINKEDIN_JOB_POSTING_SELECTORS["TITLE_AND_URL"]).first
            title = title_and_url_loc.inner_text()
            url = str(title_and_url_loc.get_attribute('href'))
            match = re.search(ID_EXTRACTOR_RE_STR, url)
            if not url or not match:
                # we can't get an id, log and move on
                logger.error(f"Unable to read an Id from URL string {url}")
                return

            result_id = match.group(1)

            jd_loc = jp_frame.locator(LINKEDIN_JOB_POSTING_SELECTORS["JD"])
            jp = LinkedInRawJobPosting(
                source=Source.LINKEDIN,
                result_id=result_id,
                last_found_in=parsing_session_id,
                url=Url(url),
                title=title,
                jd_text=jd_loc.inner_text(),
                jd_html=jd_loc.inner_html()
                )

        except: # TODO: I'm not sure what I'm catching for, need to do some trial and error
            raise JobPostingExtractionError("we will raise like this if we can't parse a card!")

        self._repo.add(jp)
