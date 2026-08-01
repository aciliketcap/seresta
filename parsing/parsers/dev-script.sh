#!/usr/bin/bash
set -euo pipefail

echo "STARTED THE CONTAINER"

on_error() {
    # print issue and close the dev container on error
    local exit_code=$?
    local line_no=$1
    echo "ERROR: Dev environment could not be set up!!!"
    echo "Script failed at line ${line_no} with exit code ${exit_code}" >&2
    echo "Failed command: ${BASH_COMMAND}" >&2
    exit "${exit_code}"
}
trap 'on_error ${LINENO}' ERR

# create .venv from the container image if it doesn't exist (or if uv.lock is deleted)
# we need to use --system-site-packages because all pw related things are there
if ! grep -q -e 'home = /usr/bin' .venv/pyvenv.cfg; then
    echo "Setting up .venv for dev"
    rm -rf .venv && \
    uv venv --system-site-packages --no-managed-python && \
    uv sync --all-groups
    # note that the python version in pyproject.toml files must match the python version of the interpreter in the Docker image's system
fi

source .venv/bin/activate
export PYTHONPATH=/opt/serespar/src

# ok, we're set
set +e
trap - ERR

MODULE_PATH="${PARSER}_${PROJECT}_parser.src"

if [[ -z "${NO_COOKIES+x}" ]]; then
    if [[ -n "${PER_TASK_COOKIES+x}" ]]; then
        if [[ ! -f "/run/secrets/${TASK}_cookies" ]]; then
            echo "/run/secrets/${TASK}_cookies not found, running initial login script..."
            cd /parsers && python -m ${MODULE_PATH}.initial_login
        fi
    else
        if [[ ! -f "/run/secrets/parser_cookies" ]]; then
            echo "/run/secrets/parser_cookies not found, running initial login script..."
            cd /parsers && python -m ${MODULE_PATH}.initial_login
        fi
    fi
fi


echo "STARTING THE PARSER WITH DEBUGPY"

# run in perpetual debug sessions
# PYTHONFAULTHANDLER=1 is added since CPython can segfault because of quite unexpected issues
# edit the last line to point to your app's entry point
# SEARCH_URL_OVERRIDE is for when you want to override for a simple thing
while true; do
    cd /parsers && PYTHONFAULTHANDLER=1 python -Xfrozen_modules=off \
    -m debugpy --listen 0.0.0.0:5678 --wait-for-client \
    -m ${MODULE_PATH}.__main__;
done

# run without debugger
# cd /parsers && python -m ${MODULE_PATH}.__main__
