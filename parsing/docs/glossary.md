# Domain-Driven Design (DDD) Glossary: `serespar` Core

This is the working copy of the glossary agreed in
[work item #1](https://gitlab.com/aciliketcap-agentic-dev/seresta/-/work_items/1).
It records **what the terms mean and where they live in the code today**, so the
vocabulary and the source stay honest with each other.

Individual Domains and Parsers keep their own localised glossaries for
business-specific terms (`car card`, `job posting`, `deal-card`, ...) and link
back here. On disk a Domain is carried by a *project* — see
[Project vs Domain](#project-vs-domain).

**Exceptions** all derive from `SeresparException` in
`serespar/exceptions.py`; every subclass lives in the module whose code raises
it -- except the two sync-barrier timeouts, whose component does not exist yet,
which wait in `exceptions.py`. `serespar/__init__.py` re-exports all of them.
They are listed with their section here rather than in a section of their own.
Several are declared ahead of the component that will raise them; those say so.

**How to read this:** each section lists the terms that exist in code, with
where to find them, followed by the terms from the same section that are still
only names. The latter are the backlog for the architecture follow-up; each one
also has a `TODO` at the place in the code where the behaviour is currently
open-coded.

---

## 1. Initiation & Orchestration

* **`ParsingSession`** — `serespar/parsing_session.py`. The core orchestrator: it
  opens the browser, applies the `OriginQuery`, and drives the main loop over
  `PaginationBatch`es and their results. Subclassed per project
  (`BaseUsedCarListingParsingSession`, `BaseJobPostingsParsingSession`) and then
  per site (`CarWowParsingSession`, ...).
* **`OriginUrl`** — the base web address where the session enters the target
  website. The `origin_url` constructor argument of `ParsingSession`,
  `ParserConfig.base_origin_url` (`SERESPAR_BASE_ORIGIN_URL` in a parser's
  `.env`), and the `source.origin_url` column.
* **`OriginQuery`** — the domain representation of the search parameters. Only
  carwow has one so far: `CarWowOriginQuery` in
  `carwow_used_car_listing_parser/config.py`, holding the postcode, the price
  range, the age range, the fuel types and the transmission, i.e. everything
  `process_origin_query` types into the filter forms.
* **`OriginQueryProcess`** — `ParsingSession.process_origin_query()`. The base
  implementation just navigates to the `OriginUrl`; carwow overrides it to fill
  the filter forms by hand.

* **`ConfigurationException`** — `serespar/config.py`. Raised when the config
  layers do not add up to a usable configuration, and when the Postgres
  bootstrap is missing an environment variable.
* **`QueryProcessException`** — `serespar/parsing_session.py`. Declared;
  nothing raises it yet.

**Not in the code yet:** `ParsingTask` (exists only as a `<task>.env` file and
the `TASK` variable), `ParsingSessionBuilder` (there is no DI — each parser's
`__main__.py` hand-wires everything). `OriginQueryProcess` is a method on the
session rather than an injectable component that takes an `OriginQuery`.

## 2. Authentication & Security

* **`AuthMaterial`** — the tangible proof of authentication. In practice a
  cookie file: `ParsingSession(auth_material_path=...)` loads it into the
  browser context, `serespar.save_login_cookies()` writes it, and a parser
  says where it is with `auth_material_path` on its config layer (carwow) or
  `--auth-material-path` (the parsers not moved over yet).

* **`StaleAuthMaterialException`** — `serespar/parsing_session.py`. Raised by
  `ParsingSession.__enter__` when the cookie file cannot be loaded into the
  browser context.
* **`AuthenticationFailedException`** — `serespar/cookie_saver.py`, next to the
  manual `LoginProcess`. Declared; nothing raises it yet.

**Not in the code yet:** the whole `AuthFlow` hierarchy — `NoAuthFlow`,
`ActiveFlow`, `LoginProcess`, `AuthCredentials`, `PassiveFlow`,
`CookiePassiveFlow`, `RefreshTokenPassiveFlow`. Today
`ParsingSession` injects a cookie file directly, which is a hardwired
`CookiePassiveFlow` with no abstraction; `save_login_cookies` is a manual
`LoginProcess` where the developer types the credentials into the browser
themselves.

## 3. Configuration & Cascading Hierarchy

The layered configuration and secrets, cascading `Core` -> `Project` ->
`Parser` -> `Task`, where a more specific layer overrides a more general one.

* **`CoreConfig`**, **`ProjectConfig`**, **`ParserConfig`**, **`TaskConfig`** —
  `serespar/config.py`. One pydantic model per layer, in serespar because every
  derived component has them. `CoreConfig` supersedes the `EngineConfig` name of
  the original glossary. `TaskConfig` is a `pydantic_settings.BaseSettings`, so
  one run's parameters can come straight from the environment with the
  `SERESPAR_` prefix.
* **`ConfigCascade`** / **`EffectiveConfig`** — `serespar/config.py`.
  `ConfigCascade.resolve()` merges the four layers, most general first, into the
  flat `EffectiveConfig` the rest of the code reads. Only values *explicitly
  set* on a layer override the layers below, so a field left at its default
  never clobbers a configured one — the same rule Docker Compose applies to
  layered `env_file`s. To override a lower layer's field, subclass that layer's
  model and redeclare it; `EffectiveConfig` accepts the extra fields. A layer
  set that does not add up raises `ConfigurationException`.
* **`MaxDepth` across layers** — the project sets `default_max_depth`, a task
  overrides it with `max_depth`, and after resolution `max_depth` is the single
  answer.
* **Where defaults live** — on the config models, never as literals at the
  point of use. `CoreConfig` carries the viewport size and the absolute
  timeout, `ProjectConfig` the Postgres port and sslmode,
  `CarWowParserConfig` the waits, the retry counts and how deep to paginate.
  Code reads them off the resolved config.
* **Per project and per parser layers** —
  `base_used_car_listing_parser/config.py` holds `UsedCarListingProjectConfig`;
  `carwow_used_car_listing_parser/config.py` holds `CarWowParserConfig`,
  `CarWowTaskConfig`, `CarWowOriginQuery` and `carwow_config()`, which resolves
  the whole cascade for a run. A layer subclass states its own defaults, and
  those *do* override the layers below -- that is the difference between a
  default a layer declares and one it merely inherits.
* **The environment follows the models** — `CoreSettings`, `ProjectSettings`
  and `ParserSettings` read one layer from the environment, and every variable
  is the name `BaseSettings` derives from the field itself:
  `SERESPAR_DB_HOST`, `SERESPAR_DB_NAME`, `SERESPAR_DB_PORT`,
  `SERESPAR_DB_SSLMODE`, `SERESPAR_BASE_ORIGIN_URL`, `SERESPAR_MAX_DEPTH`,
  `SERESPAR_HEADLESS`, and the nested `SERESPAR_ORIGIN_QUERY__POSTCODE`,
  `SERESPAR_ORIGIN_QUERY__PRICE_MIN`, ... Credentials, which are not config,
  follow the same naming when they fall back to the environment:
  `SERESPAR_DB_USER`, `SERESPAR_DB_PASSWORD`.

  **`TASK` is the exception.** It names the task to run, selects the task's
  env file, and is what the app builder will read to decide what to build, so
  `TaskConfig.task_id` accepts it alongside `SERESPAR_TASK_ID`. `PROJECT` and
  `PARSER` are compose's own, not config.

### Project vs Domain

**The top layer of this cascade is the `Project`, not the `Domain`.** A project
(`used_car_listing`, `job_postings`) consists of several `Parser`s, and it
*models* one Domain, which every parser under it adheres to. The Domain is the
DDD concept; the project is the thing on disk that carries it. So the config
layer is named for the project — `ProjectConfig` / `ProjectSecrets`, superseding
the `DomainConfig` / `DomainSecrets` of the original glossary — while `Domain`
keeps its DDD meaning everywhere else in this document.

* **Project layer** — `dev-config/<project>/`, selected by the `PROJECT` variable.
  Holds `postgres.env` and the database secrets, i.e. the `ProjectConfig` and
  `ProjectSecrets` shared by every parser in the project. That file serves two
  containers: `POSTGRES_DB` is the database container's own (it creates the
  database with it), `SERESPAR_DB_HOST` is the parser's project layer.
* **Parser layer** — `dev-config/<project>/parsers/<parser>/parser.env`, selected
  by `PARSER`. Holds `SERESPAR_BASE_ORIGIN_URL` and the site cookies secret.
* **Task layer** — `dev-config/<project>/parsers/<parser>/<task>.env`, selected by
  `TASK`. Holds the parameters of one exact run
  (`SERESPAR_ORIGIN_QUERY__*`, `SERESPAR_MAX_DEPTH`, ...). Anything that
  identifies the person running the task -- carwow's postcode -- stays out of
  the repo and is passed in from the shell; compose forwards it.

Docker Compose layers them in that order via `env_file`, so a later file
overrides an earlier one. The same word drives the source tree:
`parsing/parsers/base_<project>_parser` and
`parsing/parsers/<parser>_<project>_parser`.

**Not wired in yet:** there is no dependency injection, so the config is
resolved at the point of use rather than built once and injected:
`ParsingSession` falls back to `CoreSettings()` when no `CoreConfig` is passed,
`serespar.db.postgres.build_engine_from_env()` reads `ProjectSettings()`, and
carwow's session and `initial_login` call `carwow_config()` /
`CarWowParserConfig()` themselves. `ConfigCascade.from_env()` is the bridge; it
disappears when app initialisation builds the layers and injects them.

**Not in the code yet:** `ProjectSecrets` / `ParserSecrets` / `TaskSecrets`.
Secrets stay out of the config models; credentials come from Docker secrets.

## 4. State & Synchronization

**Nothing in this section is a component yet.** `PageSyncBarrier`,
`ResultSyncBarrier`, `ContentUnroller`, `RetryWithBackoff` and `DelayBehavior`
all exist as behaviours, open-coded at each call site, and this is the single
biggest piece of the follow-up:

* **`PageSyncBarrier`** — pauses until the layout of the pagination batch has
  settled. Today: `locator(CAR_CARDS_CONTAINER).wait_for()` in carwow,
  `locator(CARDS_TABLE).wait_for(state="attached")` in the tests.
* **`ResultSyncBarrier`** — pauses until an individual result locator becomes
  interactive or visible. Today: carwow's `page.wait_for_function()` against a
  hand-written JS predicate, retried `result_sync_retries` times with a
  `result_sync_timeout_ms` timeout; the tests'
  `expect(cell).to_have_attribute("data-loaded", "true")`.
* **`ContentUnroller`** — forces lazy-loaded results into the viewport. Today:
  scattered `scroll_into_view_if_needed()` calls, plus LinkedIn's
  `mouse.wheel(0, 120)`.
* **`RetryWithBackoff`** — carwow retries the pagination step
  `max_next_pagination_batch_retries` times with a *fixed*
  `pagination_retry_sleep_seconds`. Configurable now, but still not backoff.
* **`DelayBehavior`** — bare `sleep(...)` calls in every parser. No humanising
  pattern, no dummy clicks or mouse jigs. carwow's are at least fed by config
  (`form_settle_seconds`, `new_page_load_wait_seconds`);
  `ParserConfig.default_delay_behavior` names the behaviour that would replace
  them.

**`BatchLoadTimeoutException`** and **`ElementRenderTimeoutException`** are
declared in `serespar/exceptions.py` -- the only two that are not with the code
that raises them, because that code does not exist yet. They move next to the
barriers once those are built. A barrier that fails surfaces a raw
`playwright.TimeoutError` today.

## 5. Traversal & Extraction

* **`ResultIndex`** — `SessionTracker.result_index`, the count within the current
  pagination batch.
* **`PaginationIndex`** — `SessionTracker.pagination_index`, the current loop
  iteration over the paginated sets.
* **`SessionTracker`** — `serespar/base_extractor.py`. **Note:** this is the old
  `ParseItemContext` under its new name and is still *per-result*, whereas the
  glossary's `SessionTracker` (§7) is session-scoped and stateful. Renamed now,
  reshaped later.
* **`ResultLocator`** — the Playwright representation of the physical HTML node.
  What `ParsingSession.results_in_pagination_batch()` yields and what
  `BaseExtractor._result_locator` holds.
* **`ParsedEntity`** — the pure domain object (a pydantic model).
  `serespar/base_repos.py` holds the base with the fields every project has
  (`id`, `source`, `result_id`, `last_found_in`, `url`); `BaseRawUsedCarListing`
  adds the car fields and narrows `source` to the project's `Source` enum, and
  the per-site subclasses add theirs. `ParsedEntityT` is the type variable
  bounding it. (`BaseRawJobPosting` still carries its own copy of the shared
  fields; the job postings project has not been moved over.)
* **`EntityOrmRecord`** — the persistence representation:
  `AbstractParsedEntityORM` in `serespar/db/orm.py` carries the shared columns
  and the polymorphic mapper args, `BaseRawUsedCarListingORM` sets the table
  name and the car columns, and the per-site ORMs join onto it.
* **`BaseExtractor`** — `serespar/base_extractor.py`. The abstract foundation for
  all extraction logic; a context manager that turns a `ResultLocator` into a
  `ParsedEntity` and hands it to the repository, with the `critical_info` /
  `noncrit_info` decorators deciding whether a bad field sinks the record.

**Two ids, deliberately named differently.** `ParsedEntity.result_id` is the id
the *target website* gave the result (a string, parsed out of a URL or the
markup). `AbstractBaseRepository.get(entity_id)` takes the *repository's* own
primary key (an integer). The old code called both `seres_id`, which is exactly
the confusion this glossary is meant to remove.

* **`ParsingError`** — `serespar/base_extractor.py`. Raised by `BaseExtractor`
  when a field cannot be read out of the markup.
  **`ExtractionCriticalError`** wraps whatever a `critical_info`-decorated
  method raised, and sinks the whole `ParsedEntity`.
* **`NodeNotFoundException`**, **`EmptyLocatorException`**,
  **`UnmatchedSelectorException`** — `serespar/base_extractor.py`. The three cases
  `ParsingError` is meant to split into, so they subclass it: extractors still
  raise the undifferentiated `ParsingError`, and an `except ParsingError` keeps
  catching all three once they start being raised separately.
  `pydantic.ValidationError` does arrive natively when extracted data violates
  a `ParsedEntity`'s schema, so there is no serespar exception for that.

**Not in the code yet:** `TotalResultIndex` (nothing counts across batches),
`EntityJsonRecord`, the `SurfaceExtractor` / `ExpansionExtractor` /
`NewTabExtractor` split (carwow is a `SurfaceExtractor` by hand; LinkedIn is an
`ExpansionExtractor` split between its session and its extractor).

## 6. Navigation

* **`PaginationBatch`** — the set of search results rendered for the current
  pagination iteration. `ParsingSession.pagination_batches()` yields one
  `PaginationIndex` per batch; `results_in_pagination_batch()` walks the results
  inside it.
* **`NextPaginationTrigger`** — the DOM element the stepper clicks. Found by
  `LazyCardsParsingSession.find_next_pagination_trigger()` in the tests and by
  the equivalent inline loops in each parser.

**Not in the code yet:** `PaginationBatchStepper` as a component — every parser
reimplements "walk the pagination links, find the one whose text is current + 1,
click it" (carwow's `step_to_next_pagination_batch()` is the closest thing, and
it never verifies that the new batch actually loaded).
`PaginationControlMissingException` is declared in `serespar/parsing_session.py`
but unraised: carwow just logs and retries, and the test session raises a local
error.

## 7. Flow Control & Termination

* **`MaxDepth`** — the `max_depth` argument to `pagination_batches()`, fed by
  `TaskConfig.max_depth` (`SERESPAR_MAX_DEPTH`), which falls back to the
  project's `default_max_depth`.
* **`SessionReport`** — the start date, end date and source recorded on
  `ParsingSessionORM` / the `parsing_session` table (both in serespar now),
  written by `SessionReportRepository` in `serespar/db/repos.py`. There is no
  report *object* yet; the row is the identity of the session, and these
  columns are the beginnings of its report.

  **Naming decision.** The row names the session, not a report about it —
  `parsed_entity_in_parsing_session` and `raw_*.last_found_in` both point at it
  as the session — so the ORM and the table are `ParsingSession` /
  `parsing_session`, while the repository is named for what it records.

**Not in the code yet:** `SessionTracker` in its real, session-scoped form —
`ParsingSession.num_failed_results` is all we track, and nothing answers "should
we stop?"; `MaxDepth` is just a loop bound the caller passes. The report is never
emitted anywhere beyond the row. `AccessBlockerEncounteredException` is
declared in `serespar/parsing_session.py` but nothing detects the condition: a
CAPTCHA or unexpected login prompt just times out like any other missing
element.

## 8. Persistence

* **`DataSink`** — **a conceptual term, not a class.** The sink is the
  repository *and wherever the repository takes the data* — it may eventually
  include external processing. `ParsingSession` is the orchestrator that takes
  the domain object (a pydantic data class) and puts it into the repository;
  that whole path is the data sink. Do not expect to find a `DataSink` type.

  It *is* used as a variable name for the persistence-layer object at the
  outermost layer, where that whole path is what you are holding: `data_sink` in
  every parser's `__main__.py`. That object is headed into `ParsingSession`
  itself in the architecture refactor.
* **`AbstractBaseRepository`** — `serespar/base_repos.py`. The abstract
  `add` / `get` interface every parser's repository implements. Specialised per
  project (`AbstractBaseRawUsedCarListingRepository`,
  `AbstractBaseRawJobPostingRepository`) and implemented on SQLAlchemy
  (`BaseRawUsedCarListingSqlAlchemyRepository` and its per-site subclasses).

* **Postgres bootstrap** — `serespar/db/postgres.py`. Building the `Engine`
  from the `ProjectConfig` layer and the Docker secrets, the `sessionmaker`,
  and `init_schema`. Shared by every project; the driver packages are the
  optional `serespar[postgres]` extra, and nothing in `serespar/__init__.py`
  imports the module.
* **The declarative `Base`** — `serespar/db/orm.py`, one for everybody. Each
  project has its own database, so identical table names across projects never
  meet. `init_schema` creates that base's tables by default.
* **Shared tables** — `SourceORM` (`source`) and `ParsingSessionORM`
  (`parsing_session`) are the same everywhere and are concrete in
  `serespar/db/orm.py`. `AbstractParsedEntityInParsingSessionORM` is abstract
  only because its foreign key points at the project's own entity table, which
  the subclass names in `PARSED_ENTITY_TABLE`.
* **`SqlAlchemyEntityRepository`** — `serespar/db/repos.py`. The dedup-check,
  insert and join-row write every project's repository does;
  `BaseRawUsedCarListingSqlAlchemyRepository` only points it at the concrete
  ORM, pydantic and joining classes. `SessionReportRepository` and
  `seed_sources` live there too, the latter taking the project's seed mapping.

**Not in the code yet:** `SessionRepository` in the glossary's sense — bound to
the lifecycle of the current `ParsingSession`, staging entities in memory and
guaranteeing a final flush. The SQLAlchemy repositories are not session-bound
and open a transaction per `add()`, so there is no batch semantics and no final
flush. `SessionRepositoryException` is declared in `serespar/base_repos.py`, but
until then ORM and driver errors leak straight out to the orchestrator.
