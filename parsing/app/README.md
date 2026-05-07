# How to start developing an app?
1. Follow the instructions on [docker/README.md](docker/README.md) and create a Docker container with playwright-python and chromium browser.
2. In your terminal, go to `parsing/app` directory and create a venv with `uv sync --all-groups` there. In your IDE config, make it use `parsing/app/.venv` dir as Python environment. You may need to restart your IDE.
3. Create your app project in a direcory in app, for example `my-app`. But do the following if you want to start a brand new app project:
    1. Create a pyproject.toml. You can copy [this pyproject.toml](app/linkedin-job-postings-parser/pyproject.toml). Critical part is the `[tool.uv.sources]` section.
    2. Create a `__main__.py` file. Subclass `ResultsParseSession`, fill in the abstract generator methods `paginations_in_search_results` and `results_in_pagination`. You don't need to fill them in immediately, it's probably a good idea to first see the web site in playwright browser first. Run your class which inherits from `ResultsParseSession` like below:
    ```
    with MyParseSession("https://my-url.com") as session:
      print("Opened the web site in playwright's chromium browser!")
    ```
    and put a breakpoint in print statement.
4. Run the container with the following command:
    ```
    # in parsing/ dir
    docker run --rm -it \
    -e DISPLAY -v /tmp/.X11-unix:/tmp/.X11-unix \
    -v ./serespar:/opt/serespar \
    -v ./app/:/app \
    -w /app/my-app \
    -p 5678:5678 \
    playwright:localbuild-noble-20260113-v1.57.0 \
    /bin/bash --init-file /app/dev-script.sh
    ```
5. Start the app from the container's shell:
    ```
    cd /app && python -Xfrozen_modules=off \
    -m debugpy --listen 0.0.0.0:5678 --wait-for-client \
    -m my-app 'your-search-url'
    ```

    1. Alternatively you can use docker compose with database containers and such, an example [here](docker/docker-compose.yml).
6. In your IDE setup debugpy client. For VS code or Cursor you can copy and use [the example config](../utils/example-remote-debug-vscode). Don't forget to edit the pathMappings for your app!
7. Start the debugpy client and it should open your URL in the playwright browser and stop at the breakpoint. 

**Note that** linkedin-job-postings-parser project is a bit complicated with a base project and repo pattern and pydantic models lying around. TODO: I'll bring along a simple test project, which will be used in some basic integration tests as well.

# How to push to production?
TODO: I'll write this when I tidy up my prod and work something out which would work for most people.

# TODOs related to all apps
- setting the browser viewport to smt larger than the defaults can be useful!
- making sure locators return single things or throwing will prevent issues in the long run
- replace the bootstrap `Base.metadata.create_all(engine)` call in `init_schema` with proper Alembic migrations
- add a Postgres healthcheck on the `postgres` service in `parsing/docker/docker-compose.yml` and connection retries around `build_engine_from_env` so the parser container waits for the DB to be ready
- add a database index on `raw_job_posting.processed` (the column queried by `find_all_by_processed`)
