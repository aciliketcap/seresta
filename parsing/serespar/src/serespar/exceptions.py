"""The root of the `serespar` exception taxonomy.

Only the base class, and the two whose component does not exist yet, live
here. **Every other subclass is defined in the module whose code raises it** -- `ConfigurationException` in `config.py`, the extraction
errors in `base_extractor.py`, and so on -- so an exception and the code that
throws it stay next to each other. `serespar/__init__.py` re-exports them all,
so `from serespar import ParsingError` works wherever they live.

The sections of `parsing/docs/glossary.md` list which exception belongs to
which module.
"""


class SeresparException(Exception):
    """Base exception for all domain errors."""


# The sync barriers are the exception: `PageSyncBarrier` and `ResultSyncBarrier`
# do not exist yet, so their failures have no module to live in. They wait here
# until those components are built.


class BatchLoadTimeoutException(SeresparException):
    """A `PageSyncBarrier` gave up waiting for the `PaginationBatch` layout.

    TODO: moves next to `PageSyncBarrier` once that exists. Nothing raises it
    yet -- a barrier that fails surfaces a raw `playwright.TimeoutError`.
    """


class ElementRenderTimeoutException(SeresparException):
    """A `ResultSyncBarrier` gave up waiting for one result to render.

    TODO: same as above, for `ResultSyncBarrier`.
    """
