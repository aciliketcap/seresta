#!/usr/bin/bash
set -euo pipefail

echo $(date -Is) "STARTED TEST SCRIPT"

on_error() {
    # print issue and close the test container on error
    local exit_code=$?
    local line_no=$1
    echo "ERROR: Test environment could not be set up!!!"
    echo "Script failed at line ${line_no} with exit code ${exit_code}" >&2
    echo "Failed command: ${BASH_COMMAND}" >&2
    exit "${exit_code}"
}
trap 'on_error ${LINENO}' ERR

rm -rf .venv
uv venv --system-site-packages --no-managed-python && \
uv sync --all-groups

source .venv/bin/activate
export PYTHONPATH=/opt/serespar/src

# ok, we're set
set +e
trap - ERR



