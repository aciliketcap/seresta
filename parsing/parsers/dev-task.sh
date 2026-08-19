MODULE_PATH="${PARSER}_${PROJECT}_parser.src"

task() {
    # Dev sessions are for watching the parser work, so always show the window.
    # Deliberately not overridable: this task is useless without a browser to
    # look at. Drop this line if you ever need a headless dev run.
    export SERESPAR_HEADLESS=0

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

    # run the task in perpetual debug sessions
    # PYTHONFAULTHANDLER=1 is added since CPython can segfault because of quite unexpected issues
    # you can add --log-to-stderr to debugpy params to troubleshoot things like breakpoints not working because of mismatched local and remote dirs
    while true; do
        cd /parsers && PYTHONFAULTHANDLER=1 python -Xfrozen_modules=off \
        -m debugpy --listen 0.0.0.0:5678 --wait-for-client \
        -m ${MODULE_PATH}.__main__;
    done

    # run without debugger
    # cd /parsers && python -m ${MODULE_PATH}.__main__
}
