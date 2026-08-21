"""The default `OriginQueryProcess`.

The `OriginQuery` is the domain representation of a search: a postcode, a price
range, whatever the site lets you ask for. The `OriginQueryProcess` is what
turns it into results on screen, and it is a strategy the composition root
injects into the session, because how a site takes a query is a property of
that site and nothing else.

Most sites encode the whole query in the URL, which is what this module does.
A site that only takes it through its own filter widgets gets a process of its
own -- see `CarWowFilterFormsQueryProcess` -- without the session knowing the
difference.
"""

import logging

from playwright.sync_api import Page

logger = logging.getLogger(__name__)


class NavigateToOriginUrl:
    """Open the `OriginUrl` and let the results come up.

    The default process: the `OriginQuery` is already in the URL, so there is
    nothing to fill in.
    """

    def __init__(self, origin_url: str) -> None:
        self._origin_url = origin_url

    def open_results(self, page: Page) -> None:
        page.goto(self._origin_url, wait_until="load")
        logger.info("URL `%s` should be loaded now.", self._origin_url)
