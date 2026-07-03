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
export SECRETS_DIR=/app/dev-secrets/carwow_used_car_listing_parser

# ok, we're set
set +e
trap - ERR

# TODO: make this generic for all apps that need to login and acquire cookies first
if [ ! -f "$SECRETS_DIR/carwow_cookies.json" ]; then
    echo "carwow_cookies.json not found, running initial login script..."
    cd /app && python -m carwow_used_car_listing_parser.src.initial_login
fi


echo "STARTING THE APP WITH DEBUGPY"

# run in perpetual debug sessions
# PYTHONFAULTHANDLER=1 is added since CPython can segfault because of quite unexpected issues
# edit the last line to point to your app's entry point
while true; do
    cd /app && PYTHONFAULTHANDLER=1 python -Xfrozen_modules=off \
    -m debugpy --listen 0.0.0.0:5678 --wait-for-client \
    -m carwow_used_car_listing_parser.src.__main__ "$SEARCH_URL";
done

# run without debugger
# cd /app && python -m linkedin-job-postings-parser.src.__main__ "$SEARCH_URL"
