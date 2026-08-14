task() {
    echo TEST TASK STARTED
    # Headless unless the caller asked otherwise, so the suite runs on a box
    # with no X display: SERESPAR_HEADED=1 podman compose up
    # Values kept in step with headed_from_env() in serespar/parsing_session.py.
    # Assign through a default first: init.sh runs under `set -u`, so expanding
    # an unset SERESPAR_HEADED directly would kill the task.
    local headed="${SERESPAR_HEADED:-}"
    case "${headed,,}" in
        1|true|yes|on) echo "Browser mode: headed" ;;
        *)             echo "Browser mode: headless" ;;
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



