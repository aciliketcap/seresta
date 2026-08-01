# Project structure
This directory contains a library and apps that use (ie. depend on) that library.

Also this library and apps can't be run with mere uv .venv's. Well technically they can but you playwright library depends on it's own browsers and stuff. Not only they're bulky (and we don't need most of them) but also they have their own dependencies which needs to be installed on your own system.

Therefore I have opted to minimize and keep all playwright-python dependencies in a separate Docker image. I run my code inside Docker containers during the development phase as well.

All this results in a little bit complex development environment.

## `docker/` directory:
Contains the manual instructions and Dockerfiles to create the playwright docker image. It is taken from [Microsoft's playwright-python repo](https://github.com/microsoft/playwright-python). You can possibly use [Microsoft's own playwright-python Docker image](https://hub.docker.com/r/microsoft/playwright-python) as well but it also has all the dependencies and too bulky to use in production.

# `app/pyproject.toml` file:
Dependencies are grouped here.
local-ide-needs: We install everything into our Docker image but the IDE running on the host still needs a shallow copy of the dependencies so that the internal linter doesn't underline the whole code with "xxx is not defined" errors. Not necessary inside container since we already have native playwright there.
test-and-lint: For static checks and tests running inside the (test) container to determine prod container health.
dev: Debugpy for dev containers. Must not be included in prod containers!!!

# `app/dev-script.sh` script:
This script is run on each invocation of a development container. It checks if the .venv exists and if not creates it.

Note that we use the `--system-site-packages` because the playwright system dependencies are directly installed in the Python environment of the system.

# `app/my-app/pyproject.toml` file:
This is the file [app/dev-script.sh](app/dev-script.sh) uses to create the .venv for your app project.

1. Since werely on the playwright browser inside the container image's system directories dev-script creates this environment with `--system-site-packages --no-managed-python` parameters.
2. Since the .venv is created from within the docker container and relies on the system python inside, you shouldn't use that .venv for your IDE. You should instead go to `app` and use [the pyproject.toml there](app/pyproject.toml) to create a .venv and set that one as your Python interpreter in your IDE.
  - Also directories in the project structure and inside container image are different and [you can't quite manage it in uv yet](https://stackoverflow.com/questions/79471982/uv-index-and-path-for-the-same-dependency-in-one-pyproject-toml-file).

