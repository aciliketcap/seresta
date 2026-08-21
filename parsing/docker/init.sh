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

if [ -f "$TASK_STARTER_SCRIPT_PATH" ]; then
    source "$TASK_STARTER_SCRIPT_PATH"
else
    source task.sh
fi

start_task

