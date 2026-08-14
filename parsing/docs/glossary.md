# Domain-Driven Design (DDD) Glossary: `serespar` Core

This is the working copy of the glossary agreed in
[work item #1](https://gitlab.com/aciliketcap-agentic-dev/seresta/-/work_items/1).
It records **what the terms mean and where they live in the code today**, so the
vocabulary and the source stay honest with each other.

Individual Domains and Parsers keep their own localised glossaries for
business-specific terms (`car card`, `job posting`, `deal-card`, ...) and link
back here. On disk a Domain is carried by a *project* — see
[Project vs Domain](#project-vs-domain).

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
  website. The `origin_url` constructor argument of `ParsingSession`, the
  `ORIGIN_URL` variable in a parser's `.env`, and the `source.origin_url` column.
* **`OriginQuery`** — the domain representation of the search parameters. Only
  carwow has one so far (`carwow_used_car_listing_parser.OriginQuery`), holding
  the postcode.
* **`OriginQueryProcess`** — `ParsingSession.process_origin_query()`. The base
  implementation just navigates to the `OriginUrl`; carwow overrides it to fill
  the filter forms by hand.

**Not in the code yet:** `ParsingTask` (exists only as a `<task>.env` file and
the `TASK` variable), `ParsingSessionBuilder` (there is no DI — each parser's
`__main__.py` hand-wires everything), `ConfigurationException`,
`QueryProcessException`. `OriginQueryProcess` is a method on the session rather
than an injectable component that takes an `OriginQuery`.

## 2. Authentication & Security

* **`AuthMaterial`** — the tangible proof of authentication. In practice a
  cookie file: `ParsingSession(auth_material_path=...)` loads it into the
  browser context, `serespar.save_login_cookies()` writes it, and the parsers
  point at it with `AUTH_MATERIAL_FILE` / `--auth-material-path`.

**Not in the code yet:** the whole `AuthFlow` hierarchy — `NoAuthFlow`,
`ActiveFlow`, `LoginProcess`, `AuthCredentials`, `PassiveFlow`,
`CookiePassiveFlow`, `RefreshTokenPassiveFlow` — plus
`AuthenticationFailedException` and `StaleAuthMaterialException`. Today
`ParsingSession` injects a cookie file directly, which is a hardwired
`CookiePassiveFlow` with no abstraction; `save_login_cookies` is a manual
`LoginProcess` where the developer types the credentials into the browser
themselves.

## 3. Configuration & Cascading Hierarchy

The layered configuration and secrets, cascading `Project` -> `Parser` -> `Task`.
The cascade exists, but only as directory layout and env files — there are no
config objects.

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
  `ProjectSecrets` shared by every parser in the project.
* **Parser layer** — `dev-config/<project>/parsers/<parser>/parser.env`, selected
  by `PARSER`. Holds the `ORIGIN_URL` and the site cookies secret.
* **Task layer** — `dev-config/<project>/parsers/<parser>/<task>.env`, selected by
  `TASK`. Holds the parameters of one exact run.

Docker Compose layers them in that order via `env_file`, so a later file
overrides an earlier one. The same word drives the source tree:
`parsing/parsers/base_<project>_parser` and
`parsing/parsers/<parser>_<project>_parser`.

**Not in the code yet:** `EngineConfig`, `ProjectConfig`/`ProjectSecrets`,
`ParserConfig`/`ParserSecrets`, `TaskConfig`/`TaskSecrets` as actual types.
`EngineConfig` material (viewport size, headless mode, network limits) is
hardcoded in `ParsingSession` or read straight from the environment
(`SERESPAR_HEADED`); carwow's price / age / fuel / gearbox filters are hardcoded
in `process_origin_query` where they belong to a `TaskConfig`.

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
  hand-written JS predicate, retried three times; the tests'
  `expect(cell).to_have_attribute("data-loaded", "true")`.
* **`ContentUnroller`** — forces lazy-loaded results into the viewport. Today:
  scattered `scroll_into_view_if_needed()` calls, plus LinkedIn's
  `mouse.wheel(0, 120)`.
* **`RetryWithBackoff`** — carwow retries the pagination step three times with a
  *fixed* one-second sleep. Not backoff.
* **`DelayBehavior`** — bare `sleep(...)` calls in every parser. No humanising
  pattern, no dummy clicks or mouse jigs.

**Not in the code yet:** also `BatchLoadTimeoutException` and
`ElementRenderTimeoutException`; a barrier that fails currently surfaces a raw
`playwright.TimeoutError`.

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
* **`ParsedEntity`** — the pure domain object (a pydantic model):
  `BaseRawUsedCarListing`, `BaseRawJobPosting` and their per-site subclasses.
  `ParsedEntityT` is the type variable bounding it.
* **`EntityOrmRecord`** — the persistence representation: `BaseRawUsedCarListingORM`,
  `BaseRawJobPostingORM` and the joined-table subclasses.
* **`BaseExtractor`** — `serespar/base_extractor.py`. The abstract foundation for
  all extraction logic; a context manager that turns a `ResultLocator` into a
  `ParsedEntity` and hands it to the repository, with the `critical_info` /
  `noncrit_info` decorators deciding whether a bad field sinks the record.

**Two ids, deliberately named differently.** `ParsedEntity.result_id` is the id
the *target website* gave the result (a string, parsed out of a URL or the
markup). `AbstractBaseRepository.get(entity_id)` takes the *repository's* own
primary key (an integer). The old code called both `seres_id`, which is exactly
the confusion this glossary is meant to remove.

**Not in the code yet:** `TotalResultIndex` (nothing counts across batches),
`EntityJsonRecord`, the `SurfaceExtractor` / `ExpansionExtractor` /
`NewTabExtractor` split (carwow is a `SurfaceExtractor` by hand; LinkedIn is an
`ExpansionExtractor` split between its session and its extractor), and the
exception taxonomy `NodeNotFoundException` / `EmptyLocatorException` /
`UnmatchedSelectorException` — today all three collapse into one `ParsingError`,
which `ExtractionCriticalError` wraps when the field was critical.
`pydantic.ValidationError` does arrive natively when extracted data violates a
`ParsedEntity`'s schema.

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
it never verifies that the new batch actually loaded). Also
`PaginationControlMissingException`: carwow just logs and retries, and the test
session raises a local error.

## 7. Flow Control & Termination

* **`MaxDepth`** — the `max_depth` argument to `pagination_batches()`, fed by the
  `MAX_DEPTH` environment variable.
* **`SessionReport`** — the start date, end date and source recorded on
  `ParsingSessionORM` / the `parsing_session` table, written by
  `SessionReportRepository`. There is no report *object* yet; the row is the
  identity of the session, and these columns are the beginnings of its report.

  **Naming decision.** The row names the session, not a report about it —
  `parsed_entity_in_parsing_session` and `raw_*.last_found_in` both point at it
  as the session — so the ORM and the table are `ParsingSession` /
  `parsing_session`, while the repository is named for what it records.

**Not in the code yet:** `SessionTracker` in its real, session-scoped form —
`ParsingSession.num_failed_results` is all we track, and nothing answers "should
we stop?"; `MaxDepth` is just a loop bound the caller passes. The report is never
emitted anywhere beyond the row. `AccessBlockerEncounteredException` does not
exist: a CAPTCHA or unexpected login prompt just times out like any other missing
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

**Not in the code yet:** `SessionRepository` in the glossary's sense — bound to
the lifecycle of the current `ParsingSession`, staging entities in memory and
guaranteeing a final flush. The SQLAlchemy repositories are not session-bound
and open a transaction per `add()`, so there is no batch semantics and no final
flush. `SessionRepositoryException` does not exist either: ORM and driver errors
leak straight out to the orchestrator.
