from .app import AppNotOpenException, ParserApp, SessionReport
from .builder import AppAssemblyException, ParserBuilder
from .origin_query import NavigateToOriginUrl
from .ports import (
    EntityRepository,
    ExtractorFactory,
    OriginQueryProcess,
    ResultExtractor,
    SessionReporter,
)
from .parsing_session import (
    ParsingSession,
    AccessBlockerEncounteredException,
    PaginationControlMissingException,
    QueryProcessException,
    StaleAuthMaterialException,
)
from .cookie_saver import save_login_cookies, AuthenticationFailedException
from .base_repos import AbstractBaseRepository, ParsedEntity, SessionRepositoryException
from .base_extractor import (
    SessionTracker,
    BaseExtractor,
    EmptyLocatorException,
    ExtractionCriticalError,
    NodeNotFoundException,
    ParsingError,
    UnmatchedSelectorException,
)
from .config import (
    ConfigCascade,
    ConfigurationException,
    CoreConfig,
    EffectiveConfig,
    ParserConfig,
    ProjectConfig,
    TaskConfig,
)
from .exceptions import (
    BatchLoadTimeoutException,
    ElementRenderTimeoutException,
    SeresparException,
)

__all__ = [
    # the application and the composition root, see app.py and builder.py
    "ParserApp",
    "ParserBuilder",
    "SessionReport",
    # ports, see ports.py
    "EntityRepository",
    "SessionReporter",
    "OriginQueryProcess",
    "ResultExtractor",
    "ExtractorFactory",
    "NavigateToOriginUrl",
    "ParsingSession",
    "save_login_cookies",
    "AbstractBaseRepository",
    "ParsedEntity",
    "BaseExtractor",
    "SessionTracker",
    # config layers, see config.py
    "CoreConfig",
    "ProjectConfig",
    "ParserConfig",
    "TaskConfig",
    "EffectiveConfig",
    "ConfigCascade",
    # exceptions: the base is in exceptions.py, each subclass lives with the
    # code that raises it
    "SeresparException",
    "ConfigurationException",
    "QueryProcessException",
    "AuthenticationFailedException",
    "StaleAuthMaterialException",
    "BatchLoadTimeoutException",
    "ElementRenderTimeoutException",
    "ParsingError",
    "ExtractionCriticalError",
    "NodeNotFoundException",
    "EmptyLocatorException",
    "UnmatchedSelectorException",
    "PaginationControlMissingException",
    "AccessBlockerEncounteredException",
    "SessionRepositoryException",
    "AppAssemblyException",
    "AppNotOpenException",
    ]
