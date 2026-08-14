from pydantic_core import Url
from pydantic import BaseModel
from pydantic.dataclasses import dataclass
import functools
import logging
from typing import Self, TypeVar
from playwright.sync_api import Locator, Page

from .base_repos import ParsedEntityT

logger = logging.getLogger(__name__)

class ExtractionCriticalError(Exception):
    pass

class ParsingError(Exception):
    pass
@dataclass
class SessionTracker:
    """Where we are in the parsing process, used for logging and error reporting.

    ``pagination_index`` is the current `PaginationBatch` and ``result_index``
    the position within it.

    TODO: this is the old per-result `ParseItemContext` under its new name. The
    real `SessionTracker` is session-scoped and stateful, tracks limits and
    errors and answers "should we stop?"; it should absorb the session's
    ``num_failed_results`` and start counting a `TotalResultIndex`.
    """
    parsing_session_id: int
    pagination_index: int
    result_index: int

# It's not possible to define RepoT as a variant of AbstractBaseRepository[ParsedEntityT] in Python, type bounds can't be generics :(

class BaseExtractor[RepoT, ParsedEntityT]:
    """Context manager to extract a `ParsedEntity` from a `ResultLocator` and persist it in the repository. Or properly log if there is an issue.

    ``parsing_session_id`` is stored on the listing's ``last_found_in`` field and
    used to link the result to the current parsing session.

    TODO: the `SurfaceExtractor` / `ExpansionExtractor` / `NewTabExtractor`
    split does not exist yet; concrete extractors do all three by hand.
    """
    def __init__(
        self,
        repo: RepoT,
        page: Page,
        result_locator: Locator,
        tracker: SessionTracker
        ) -> None:
        self._repo = repo
        self._parsed_entity: ParsedEntityT | None = None
        self._page = page
        self._result_locator = result_locator
        self._tracker = tracker

    def __enter__(self) -> Self:
        # do nothing
        self._critical_failure = False
        self._parsed_entity = None
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        """If something goes wrong when extracting a critical field (such as the id) then the whole record is discarded."""
        if exc_type: # left case
            # TODO: I want more info to be provided about what it was able to collect and what caused the critical failure by the subclasses!
            logger.exception("A critical field couldn't be parsed, discarding the result %s in pagination batch %s!", self._tracker.result_index, self._tracker.pagination_index)
            return False
        else: # right case
            if self._parsed_entity is not None:
                self._repo.add(self._parsed_entity)
                return True
            else: # code should not reach here, this branch is for suppressing mypy error
                logger.critical("Unable to find the extracted info to record for result %s in pagination batch %s!", self._tracker.result_index, self._tracker.pagination_index)
                return False

    @staticmethod
    def noncrit_info(error_value=None):
        """If some extra fields couldn't be extracted then the issue is logged and the code moves on."""
        def decorator(parsing_func):
            @functools.wraps(wrapped=parsing_func)
            def wrapper(self, *args, **kwargs):
                try:
                    return parsing_func(self, *args, **kwargs)
                except Exception as exc:
                    logger.exception("Failed to parse info via `%s` method of class `%s` for result %s in pagination batch %s", parsing_func.__name__, self.__class__.__name__, self._tracker.result_index, self._tracker.pagination_index)
                    return error_value
            return wrapper
        return decorator

    @staticmethod
    def critical_info(parsing_func):
        @functools.wraps(wrapped=parsing_func)
        def wrapper(self, *args, **kwargs):
            try:
                return parsing_func(self, *args, **kwargs)
            except Exception as exc:
                raise ExtractionCriticalError(
                    f"Failed to parse critical info via `{parsing_func.__name__}` method of class `{self.__class__.__name__}` for result {self._tracker.result_index} in pagination batch {self._tracker.pagination_index}"
                ) from exc
        return wrapper

    # TODO: let's think if we can monkeypatch the functions below into PW locators directly, like extension classes

    def text_at_selector(self, selector) -> str:
        # I wish I could do monads here :(
        maybe_str = self._result_locator.locator(selector).first.text_content()
        if not maybe_str:
            raise ParsingError(f"The selector {selector} did not yield a string.")

        return maybe_str.strip()

    def text_at_locator(self, locator) -> str:
        maybe_str = locator.first.text_content()
        if not maybe_str:
            raise ParsingError(f"The locator {locator} did not yield a string.")

        return maybe_str.strip()

    @staticmethod
    def try_href_attr(locator, base_url) -> Url:
        try:
            maybe_url_str = locator.get_attribute('href')
        except Exception as exc:
            raise ParsingError(f"Unable to read the `href` attribute of {locator}") from exc

        if not maybe_url_str:
            raise ParsingError(f"Unable to get the URL for locator {locator}")

        try:
            return Url(base_url + maybe_url_str)
        except Exception as exc:
            raise ParsingError(f"Unable to parse the `href` attribute \"{base_url + maybe_url_str}\" of {locator} into a valid URL") from exc
        

    def url_from_link_elt(self, other_link_elt=None, base_url="") -> Url:
        """Give the url of the `ResultLocator`, which is itself a link elt locator sometimes. Otherwise give the url in the link elt in param

        ``base_url`` is the prefix relative hrefs are resolved against, not the session's `OriginUrl`.
        """
        maybe_url_str = None
        if other_link_elt:
            return BaseExtractor.try_href_attr(other_link_elt, base_url)
        else:
            return BaseExtractor.try_href_attr(self._result_locator, base_url)



            

