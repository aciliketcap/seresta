"""The cascading configuration hierarchy.

Four layers, from the most general to the most specific:

    `CoreConfig`  ->  `ProjectConfig`  ->  `ParserConfig`  ->  `TaskConfig`

They live here, in serespar, because every derived component has them: a
project owns several parsers, a parser runs many tasks, and all of them run on
the same engine. See `parsing/docs/glossary.md` section 3 for what belongs in
which layer and for the `Project` vs `Domain` distinction.

**A more specific layer overrides a more general one.** `ConfigCascade.resolve()`
merges the layers in the order above into one flat `EffectiveConfig`. A value
that was *explicitly set* on a layer overrides whatever the layers below said;
a field left at its default only fills a gap, and never clobbers a value
someone actually configured further down. This mirrors what Docker Compose
already does with `env_file`, where the project, parser and task `.env` files
are layered in that same order.

A layer only carries the fields that layer decides, so most of them do not
collide. To override a field of a lower layer, subclass that layer's model and
redeclare the field::

    class UsedCarListingProjectConfig(ProjectConfig):
        headless: bool = False        # this project always wants a window

`EffectiveConfig` accepts such extra fields, so project- and parser-specific
settings survive the merge.

**Defaults belong here, not in the code.** Every default value the library
would otherwise hardcode -- viewport size, the Postgres port and sslmode, how
long to wait -- is a field default on one of these models, so it arrives
through config resolution instead of sitting as a literal at the point of use.
Projects and parsers do the same in their own `config.py`.

**The environment follows the models, not the other way round.** The
`*Settings` classes at the bottom read one layer from the environment, under
the names `BaseSettings` derives from the field itself: `SERESPAR_DB_HOST`,
`SERESPAR_BASE_ORIGIN_URL`, `SERESPAR_MAX_DEPTH`,
`SERESPAR_ORIGIN_QUERY__POSTCODE`, ... The one exception is `TASK`, which names
the task to run and is what selects the task's env file in the first place, so
`task_id` accepts it as well.

Secrets are deliberately absent: `ProjectSecrets` / `ParserSecrets` /
`TaskSecrets` stay out of these models, and credentials keep coming from Docker
secrets (see `serespar/db/postgres.py`).

TODO: `ConfigCascade.from_env()` is a bridge. Once app initialisation is done
with dependency injection the layers get built and injected there, and nothing
needs to read the environment at the point of use.
"""

from typing import Any, Self, TypeVar

from pydantic import AliasChoices, BaseModel, Field, ValidationError, model_validator
from pydantic_settings import BaseSettings

from .exceptions import SeresparException


class ConfigurationException(SeresparException):
    """A config layer is missing, unreadable or contradicts another layer."""


class CoreConfig(BaseModel):
    """The engine layer: how serespar drives the browser at all.

    Supersedes the `EngineConfig` name used in the original glossary.
    """
    headless: bool = True
    absolute_timeout_ms: int = 30000
    user_agent: str | None = None
    viewport_width: int = 1600
    viewport_height: int = 1000


class ProjectConfig(BaseModel):
    """The project layer: what every parser modelling this Domain shares.

    From the environment these are `SERESPAR_DB_HOST`, `SERESPAR_DB_PORT` and
    so on; the `POSTGRES_*` variables belong to the database container, not to
    us.
    """
    # keep db stuff even for projects which don't have RDBMS storage
    db_host: str
    db_port: int = 5432
    db_name: str
    db_sslmode: str = "disable"
    default_max_depth: int = 10


class ParserConfig(BaseModel):
    """The parser layer: what one target website needs."""
    base_origin_url: str
    default_delay_behavior: str = "human_standard"


class TaskConfig(BaseSettings):
    """The task layer: the parameters of one exact run.

    A `BaseSettings`, so a task can come straight from the environment the way
    a `<task>.env` file feeds one today: `SERESPAR_MAX_DEPTH`,
    `SERESPAR_ORIGIN_QUERY__POSTCODE`, ...

    `task_id` also answers to `TASK`, the variable that picks the task's env
    file and that the app builder will read to decide what to build.
    """
    task_id: str = Field(validation_alias=AliasChoices("task_id", "SERESPAR_TASK_ID", "TASK"))
    origin_query: dict[str, str | int | list[str]] = Field(default_factory=dict)
    max_depth: int | None = None
    auth_material_path: str | None = None

    model_config = {
        "env_prefix": "SERESPAR_",
        "env_nested_delimiter": "__",
        "populate_by_name": True,
    }


class EffectiveConfig(TaskConfig, ParserConfig, ProjectConfig, CoreConfig):
    """The result of the cascade: one flat config the rest of serespar reads.

    Inherits every layer's fields *and* their defaults, so a field nobody set
    anywhere still lands on the default declared in its own layer. Being a
    `BaseSettings` too, the environment fills in whatever the cascade left
    unset; values that came from the layers win over the environment.

    Build one with `ConfigCascade.resolve()` rather than by hand.
    """

    model_config = {
        "env_prefix": "SERESPAR_",
        "env_nested_delimiter": "__",
        # so that fields added by a subclassed layer survive the merge
        "extra": "allow",
    }

    @model_validator(mode="after")
    def _max_depth_falls_back_to_the_project_default(self) -> Self:
        """`MaxDepth` is the one field two layers name differently.

        The project sets `default_max_depth` for every parser under it and a
        task overrides it with `max_depth`; after resolution there is a single
        answer, so callers can just read `max_depth`.
        """
        if self.max_depth is None:
            self.max_depth = self.default_max_depth
        return self


class CoreSettings(BaseSettings, CoreConfig):
    """`CoreConfig` read from the environment.

    `SERESPAR_HEADLESS=0` is how a task definition asks for a visible browser
    window; unset means the `CoreConfig` default, which is headless, so a
    session works on a machine with no X display unless told otherwise.
    """

    model_config = {"env_prefix": "SERESPAR_", "populate_by_name": True}


class ProjectSettings(BaseSettings, ProjectConfig):
    """`ProjectConfig` read from the environment (`SERESPAR_DB_*`)."""

    model_config = {"env_prefix": "SERESPAR_", "populate_by_name": True}


class ParserSettings(BaseSettings, ParserConfig):
    """`ParserConfig` read from the environment (`SERESPAR_BASE_ORIGIN_URL`)."""

    model_config = {"env_prefix": "SERESPAR_", "populate_by_name": True}


EffectiveConfigT = TypeVar("EffectiveConfigT", bound=EffectiveConfig)


def _built(layer: Any, default_cls: type[BaseModel]) -> BaseModel:
    """A layer instance, from an instance, a class, or the default class."""
    candidate = default_cls if layer is None else layer
    return candidate() if isinstance(candidate, type) else candidate

# The four layer models of the hierarchy. A layer object is usually an instance
# of a *subclass* of one of these -- that subclass is where a project or parser
# states its own opinions, which is what `_fields_owned_by` looks for.
LAYER_BASES = (CoreConfig, ProjectConfig, ParserConfig, TaskConfig)


def _fields_owned_by(layer: BaseModel) -> set[str]:
    """The fields a layer declares itself, rather than inheriting from its base.

    A default declared on `CarWowParserConfig` is carwow saying "80 batches for
    this site"; the same field's default inherited from `ProjectConfig` is just
    the shape of the layer. Only the former overrides the layers below.
    """
    owned: set[str] = set()
    for klass in type(layer).__mro__:
        if klass in LAYER_BASES:
            break
        owned |= set(getattr(klass, "__annotations__", {}))
    return owned & set(type(layer).model_fields)


class ConfigCascade(BaseModel):
    """The layers of one run, and the merge that flattens them.

    Every layer is optional so a caller can resolve what it has -- but
    resolution fails if the layers between them do not supply the fields that
    have no default (`db_host`, `db_name`, `base_origin_url`, `task_id`),
    unless the environment does.
    """
    core: CoreConfig = Field(default_factory=CoreConfig)
    project: ProjectConfig | None = None
    parser: ParserConfig | None = None
    task: TaskConfig | None = None

    @classmethod
    def from_env(cls, **layers: Any) -> Self:
        """Build the cascade by reading each layer from the environment.

        The bridge until app initialisation is done with dependency injection:
        a project or parser names the layer classes it has
        (`ConfigCascade.from_env(parser=CarWowParserConfig)`, an instance works
        too) and the rest are serespar's, each read under its `SERESPAR_`
        names. A layer the environment cannot satisfy raises
        `ConfigurationException` here rather than a bare pydantic error.
        """
        try:
            return cls(
                core=_built(layers.get("core"), CoreSettings),
                project=_built(layers.get("project"), ProjectSettings),
                parser=_built(layers.get("parser"), ParserSettings),
                task=_built(layers.get("task"), TaskConfig),
            )
        except ValidationError as err:
            raise ConfigurationException(
                f"A config layer could not be read from the environment: {err}"
            ) from err

    def layers(self) -> list[BaseModel]:
        """The layers that are present, most general first."""
        return [layer for layer in (self.core, self.project, self.parser, self.task)
                if layer is not None]

    def resolve(
        self,
        *,
        effective_cls: type[EffectiveConfigT] = EffectiveConfig,  # type: ignore[assignment]
        **overrides: Any,
    ) -> EffectiveConfigT:
        """Flatten the layers into one `EffectiveConfig`.

        Later layers override earlier ones, and `overrides` -- a command line
        flag, say -- overrides all of them.

        A layer contributes a field when it was explicitly set, when the layer
        declares that field itself (a project or parser subclass stating its
        own default), or when no layer below it has the field at all. A default
        a layer merely inherited never overwrites a value configured further
        down.

        `effective_cls` is the flat model to validate into. A project or parser
        that adds fields of its own passes a subclass of `EffectiveConfig`
        mixing its layers in, and gets them back typed.
        """
        merged: dict[str, Any] = {}
        for layer in self.layers():
            decisive = layer.model_fields_set | _fields_owned_by(layer)
            for field, value in layer.model_dump().items():
                if field in decisive or field not in merged:
                    merged[field] = value
        merged.update(overrides)

        try:
            return effective_cls(**merged)
        except ValidationError as err:
            raise ConfigurationException(
                f"The config layers do not add up to a usable configuration: {err}"
            ) from err
