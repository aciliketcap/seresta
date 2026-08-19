"""The composition root: where a parsing application is put together.

Every dependency in serespar is passed to whoever needs it, and this is the one
place that decides what gets passed to what. A parser subclasses
`ParserBuilder`, names the handful of classes that are its own, and overrides a
hook wherever "which class" is not answer enough:

    class CarWowUsedCarListingParserBuilder(ParserBuilder[CarWowConfig]):
        config_cls = CarWowConfig
        session_cls = CarWowParsingSession
        extractor_cls = CarWowUsedCarListingExtractor
        ...

        def build_repository(self, config):
            return CarWowRawUsedCarListingSqlAlchemyRepository(self.sessionmaker(config))

`__main__.py` is then two lines, and a test builds the same application with
its own repository by passing one in.

**Why a builder and not a DI container.** The object graph here is small and
fixed -- a session, a repository, an extractor factory, a reporter -- and it is
built once per process. Hand-written wiring in a composition root costs a few
lines per parser and gives a type checker something to check, while an
auto-wiring container costs a dependency, a registration API and a layer of
indirection to buy resolution we do not need. If the graph ever grows
dependency chains deep enough to be tedious, a container can be slotted in
behind exactly this class, because nothing outside it knows how the wiring is
done. See `parsing/docs/di-and-config.md` for the alternatives that were
weighed.

**Nothing else may reach for the environment.** Reading `SERESPAR_*` is a
composition-root privilege: the layers are read here, resolved into one
`EffectiveConfig` here, and injected from here. A component that reads config
at the point of use is a service locator wearing a hat.
"""

import logging
from typing import Any

from pydantic import ValidationError

from .app import ParserApp
from .config import (
    ConfigCascade,
    ConfigurationException,
    CoreConfig,
    CoreSettings,
    EffectiveConfig,
    ParserConfig,
    ParserSettings,
    ProjectConfig,
    ProjectSettings,
    TaskConfig,
)
from .exceptions import SeresparException
from .origin_query import NavigateToOriginUrl
from .parsing_session import ParsingSession
from .ports import (
    EntityRepository,
    ExtractorFactory,
    OriginQueryProcess,
    ResultExtractor,
    SessionReporter,
)

logger = logging.getLogger(__name__)


class AppAssemblyException(SeresparException):
    """The builder cannot put the application together.

    A class the builder needs was never named and no hook was overridden to
    provide the object instead.
    """


class ParserBuilder[ConfigT: EffectiveConfig]:
    """Builds one `ParserApp`. Subclass it once per parser.

    The class attributes are the declarations: which config classes make up
    this parser's cascade, which session drives its site, which extractor reads
    its results, which `source` row it writes as. The `build_*` methods are the
    hooks: each has a default that works off those declarations, and any of
    them can be overridden when naming a class is not enough -- building a
    repository needs a database connection, for instance.

    One builder instance builds one application; anything it makes on the way
    (a sessionmaker, say) may be cached on `self`.
    """

    # -- declarations ------------------------------------------------------

    #: The flat model the cascade resolves into. A parser subclasses
    #: `EffectiveConfig` with its own layers so its fields come back typed.
    config_cls: type[ConfigT] = EffectiveConfig  # type: ignore[assignment]

    #: The four layers, most general first. `None` means "this application has
    #: no such layer". The defaults read the environment under `SERESPAR_*`.
    core_config_cls: type[CoreConfig] | None = CoreSettings
    project_config_cls: type[ProjectConfig] | None = ProjectSettings
    parser_config_cls: type[ParserConfig] | None = ParserSettings
    task_config_cls: type[TaskConfig] | None = TaskConfig

    #: The session that knows this site's layout, and the extractor that reads
    #: one of its results.
    session_cls: type[ParsingSession] | None = None
    extractor_cls: type[ResultExtractor] | None = None

    #: The `source` row this parser writes as; `SessionReporter.start()` takes
    #: it. Left at 0 for an application that reports nowhere.
    source_id: int = 0

    def __init__(
        self,
        *,
        config: ConfigT | None = None,
        core: CoreConfig | None = None,
        project: ProjectConfig | None = None,
        parser: ParserConfig | None = None,
        task: TaskConfig | None = None,
        repository: EntityRepository[Any] | None = None,
        session_reporter: SessionReporter | None = None,
        **config_overrides: Any,
    ) -> None:
        """Everything here overrides what the class declares.

        `config` short-circuits resolution altogether: an application that
        already knows its configuration -- a test, usually -- hands it over and
        no layer is read from anywhere. Otherwise a layer given here is used
        instead of the declared class, which is how a test supplies its own
        origin URL without an env file. `config_overrides` win over every
        layer, for the odd command-line flag.

        `repository` and `session_reporter` are ready-made adapters: passing a
        repository that keeps everything in a list is how the test application
        gets one that persists nothing.
        """
        self._config = config
        self._core = core
        self._project = project
        self._parser = parser
        self._task = task
        self._repository = repository
        self._session_reporter = session_reporter
        self._config_overrides = config_overrides

    # -- the composition root ---------------------------------------------

    def build(self) -> ParserApp:
        """Resolve the configuration, build the adapters, wire the app."""
        config = self.build_config()
        repository = self.build_repository(config)
        session = self.build_session(config)
        app = ParserApp(
            config=config,
            session=session,
            repository=repository,
            extractor_factory=self.build_extractor_factory(config, repository),
            session_reporter=self.build_session_reporter(config),
            source_id=self.source_id,
        )
        logger.info(
            "Built %s for task %s: %s over %s, results to %s",
            type(self).__name__,
            getattr(config, "task_id", "<unnamed>"),
            type(session).__name__,
            getattr(config, "base_origin_url", "<no origin url>"),
            type(repository).__name__,
        )
        return app

    # -- configuration -----------------------------------------------------

    def build_config(self) -> ConfigT:
        """The resolved `EffectiveConfig`, calculated once, up front.

        Every layer is built (from the environment, unless it was handed to the
        constructor) and the cascade is flattened. From here on the application
        has one config object and nothing reads a layer again.
        """
        if self._config is not None:
            return self._config

        cascade = ConfigCascade(
            core=self._layer(self._core, self.core_config_cls) or CoreConfig(),
            project=self._layer(self._project, self.project_config_cls),
            parser=self._layer(self._parser, self.parser_config_cls),
            task=self._layer(self._task, self.task_config_cls),
        )
        return cascade.resolve(
            effective_cls=self.config_cls, **self._config_overrides
        )

    @staticmethod
    def _layer[LayerT](given: LayerT | None, layer_cls: type[LayerT] | None) -> LayerT | None:
        """One layer: the one given, else the declared class, else nothing."""
        if given is not None:
            return given
        if layer_cls is None:
            return None
        try:
            return layer_cls()
        except ValidationError as err:
            raise ConfigurationException(
                f"The {layer_cls.__name__} layer could not be read: {err}"
            ) from err

    # -- adapters ----------------------------------------------------------

    def build_repository(self, config: ConfigT) -> EntityRepository[Any]:
        """The `DataSink` the results go to.

        Override this to open a database; pass `repository=` to the
        constructor to hand one over ready-made.
        """
        if self._repository is None:
            raise AppAssemblyException(
                f"{type(self).__name__} has no repository: override "
                f"`build_repository()` or pass `repository=` to the builder."
            )
        return self._repository

    def build_session_reporter(self, config: ConfigT) -> SessionReporter | None:
        """Where the `SessionReport` is recorded, if anywhere.

        `None` means the run is not recorded, which is what a test wants: the
        results then carry `UNREPORTED_PARSING_SESSION_ID`.
        """
        return self._session_reporter

    def build_origin_query_process(self, config: ConfigT) -> OriginQueryProcess:
        """The strategy that turns the `OriginQuery` into results on screen.

        The default opens the `OriginUrl`, which is all a site needs when its
        query fits in a URL.
        """
        return NavigateToOriginUrl(config.base_origin_url)

    def build_session(self, config: ConfigT) -> ParsingSession:
        """The `ParsingSession` for this site, with its config and strategy."""
        if self.session_cls is None:
            raise AppAssemblyException(
                f"{type(self).__name__} names no `session_cls`: it cannot know "
                f"how to walk this site's results."
            )
        return self.session_cls(
            origin_url=config.base_origin_url,
            auth_material_path=config.auth_material_path,
            config=config,
            origin_query_process=self.build_origin_query_process(config),
        )

    def build_extractor_factory(
        self, config: ConfigT, repository: EntityRepository[Any]
    ) -> ExtractorFactory:
        """Makes one extractor per result, bound to the repository.

        Overriding this is how an extractor gets anything else it needs -- a
        base URL to resolve hrefs against, say -- without the application
        knowing about it.
        """
        if self.extractor_cls is None:
            raise AppAssemblyException(
                f"{type(self).__name__} names no `extractor_cls`: it cannot "
                f"know how to read a result."
            )
        extractor_cls = self.extractor_cls

        def extractor_factory(page, result_locator, tracker) -> ResultExtractor:
            return extractor_cls(repository, page, result_locator, tracker)

        return extractor_factory
