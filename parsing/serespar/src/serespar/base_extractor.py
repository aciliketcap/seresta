from pydantic_core import Url
from pydantic import BaseModel
from pydantic.dataclasses import dataclass
import functools
import logging
from typing import Self, TypeVar
from playwright.sync_api import Locator, Page

from .base_repos import SeresT

logger = logging.getLogger(__name__)

class ExtractionCriticalError(Exception):
    pass

class ParsingError(Exception):
    pass
@dataclass
class ParseItemContext:
    """Where we are in the parsing process, used for logging and error reporting."""
    parse_session_id: int
    cur_pagi_num: int
    cur_item_num: int

# It's not possible to define RepoT as a variant of AbstractBaseRepository[SeresT] in Python, type bounds can't be generics :(

class BaseExtractor[RepoT, SeresT]:
    """Context manager to extract a record from the search result item and persist it in the repo. Or properly log if there is an issue.

    ``parse_session_id`` is stored on the listing's ``last_found_in`` field and
    used to link the result to the current parse session.
    """
    def __init__(
        self,
        repo: RepoT,
        page: Page,
        item: Locator,
        ctx: ParseItemContext
        ) -> None:
        self._repo = repo
        self._seres: SeresT | None = None
        self._page = page
        self._item = item
        self._ctx = ctx

    def __enter__(self) -> Self:
        # do nothing
        self._critical_failure = False
        self._seres = None
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        """If something goes wrong when extracting a critical field (such as the id) then the whole record is discarded."""
        if exc_type: # left case
            # TODO: I want more info to be provided about what it was able to collect and what caused the critical failure by the subclasses!
            logger.exception("A critical field couldn't be parsed, discarding the search result %s at page %s!", self._ctx.cur_item_num, self._ctx.cur_pagi_num)
            return False
        else: # right case
            if self._seres is not None:
                self._repo.add(self._seres)
                return True
            else: # code should not reach here, this branch is for suppressing mypy error
                logger.critical("Unable to find the extracted info to record for search result %s at page %s!", self._ctx.cur_item_num, self._ctx.cur_pagi_num)
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
                    logger.exception("Failed to parse info via `%s` method of class `%s` for item %s on pagi %s", parsing_func.__name__, self.__class__.__name__, self._ctx.cur_item_num, self._ctx.cur_pagi_num)
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
                    f"Failed to parse critical info via `{parsing_func.__name__}` method of class `{self.__class__.__name__}` for item {self._ctx.cur_item_num} on pagi {self._ctx.cur_pagi_num}"
                ) from exc
        return wrapper

    # TODO: let's think if we can monkeypatch the functions below into PW locators directly, like extension classes

    def text_at_selector(self, selector) -> str:
        # I wish I could do monads here :(
        maybe_str = self._item.locator(selector).first.text_content()
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
        """Give the url of the container elt, which is itself a link elt locator sometimes. Otherwise give the url in the link elt in param"""
        maybe_url_str = None
        if other_link_elt:
            return BaseExtractor.try_href_attr(other_link_elt, base_url)
        else:
            return BaseExtractor.try_href_attr(self._item, base_url)



            

