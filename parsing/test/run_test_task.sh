task() {
    echo TEST TASK STARTED
    while true; do
        echo INITIATING TEST DEBUG SESSION
        PYTHONFAULTHANDLER=1 python -Xfrozen_modules=off \
        -m debugpy --listen 0.0.0.0:5678 --wait-for-client \
        -m pytest;
    done
}



