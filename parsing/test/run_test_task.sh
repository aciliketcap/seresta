task() {
    echo TEST TASK STARTED
    # Headless unless the caller asked otherwise, so the suite runs on a box
    # with no X display: SERESPAR_HEADLESS=0 podman compose up
    # The variable is read by CoreConfig.headless in serespar/config.py; the
    # values below are the falsey ones pydantic accepts.
    # Assign through a default first: init.sh runs under `set -u`, so expanding
    # an unset SERESPAR_HEADLESS directly would kill the task.
    local headless="${SERESPAR_HEADLESS:-}"
    case "${headless,,}" in
        0|false|no|off|f|n) echo "Browser mode: headed" ;;
        *)                  echo "Browser mode: headless" ;;
    esac
    # while true; do
    #     echo INITIATING TEST DEBUG SESSION
    #     PYTHONFAULTHANDLER=1 python -Xfrozen_modules=off \
    #     -m debugpy --listen 0.0.0.0:5678 --wait-for-client \
    #     -m pytest --junitxml=/reports/results.xml;
    # done
    python -m pytest --junitxml=/reports/results.xml;
    # Hand pytest's status back to init.sh, which is the container's last
    # command, so `podman compose up --exit-code-from serespar` fails when the
    # tests do. Without this the task ends on `echo` and CI is always green.
    local pytest_status=$?
    echo TEST TASK ENDED
    return $pytest_status
}



