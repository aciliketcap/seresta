"""carwow's configuration: the parser and task layers of the cascade.

Every default this parser used to hardcode lives here -- how long to wait after
a pagination click, how many times to retry a lazily-loading card, the search
filters the `OriginQuery` applies -- so that the parsing code reads values off
a resolved config instead of carrying literals.

The layers below the parser (`CoreConfig`, `UsedCarListingProjectConfig`) come
from the environment; see `serespar/config.py` for the cascade and its override
rule. Anything an env file needs to set uses the name `BaseSettings` derives
from the field: `SERESPAR_MAX_DEPTH`, `SERESPAR_ORIGIN_QUERY__PRICE_MIN`, ...

Nothing here is read at the point of use: `CarWowUsedCarListingParserBuilder`
resolves these layers once, at start-up, and injects the resulting
`CarWowConfig` into the session, the strategy and the repository.
"""

from pydantic import BaseModel
from serespar.config import EffectiveConfig, ParserSettings, TaskConfig


class CarWowOriginQuery(BaseModel):
    """The search parameters this session applies to carwow.

    Nested inside `CarWowTaskConfig`, so the environment reaches these through
    the task layer's delimiter: `SERESPAR_ORIGIN_QUERY__PRICE_MIN` and so on.

    The postcode has no default on purpose: it is a property of whoever runs
    the task, so it comes from the environment rather than being baked into the
    source.
    """

    postcode: str
    price_min: int = 10000
    price_max: int = 18000
    age_from: int = 2020
    age_to: int = 2024
    fuel_types: list[str] = ["Petrol", "Hybrid"]
    transmission: str = "Automatic"


class CarWowParserConfig(ParserSettings):
    """The parser layer: everything true of carwow itself.

    The waits and retries are the parser's `DelayBehavior` and
    `RetryWithBackoff` settings in all but name; they move to those components
    once they exist.
    """

    base_origin_url: str = "https://www.carwow.co.uk/used-cars"
    # This parser's `AuthMaterial`: a per-parser cookie file.
    # TODO: per-task cookies, once the `AuthFlow` hierarchy exists.
    auth_material_path: str | None = "/run/secrets/parser_cookies"
    # carwow shows 12 non-ad listings per batch, so the depth is set high.
    default_max_depth: int = 80

    # `PaginationBatchStepper` settings.
    max_next_pagination_batch_retries: int = 3
    pagination_retry_sleep_seconds: float = 1
    new_page_load_wait_seconds: float = 6
    # `ResultSyncBarrier` settings: the lazily-filled turbo frame of one card.
    result_sync_timeout_ms: int = 1000
    result_sync_retries: int = 3
    # `DelayBehavior`: the pause after each filter interaction in the
    # `OriginQueryProcess`, while the page re-renders.
    form_settle_seconds: float = 2

    # The manual `LoginProcess` that writes the `AuthMaterial`.
    login_url: str = "https://www.carwow.co.uk/"
    login_success_url: str = "https://www.carwow.co.uk/"
    manual_login_seconds: int = 60


class CarWowTaskConfig(TaskConfig):
    """The task layer: one exact carwow run.

    `origin_query` has no default: a run has to say what it is searching for,
    and a missing `SERESPAR_ORIGIN_QUERY__POSTCODE` should stop the task rather
    than quietly search somewhere else.
    """

    origin_query: CarWowOriginQuery  # type: ignore[assignment]


class CarWowConfig(CarWowTaskConfig, CarWowParserConfig, EffectiveConfig):
    """The resolved cascade for a carwow run, with carwow's own fields typed."""
