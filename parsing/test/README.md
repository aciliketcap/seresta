Run test tasks by running the following command in this directory:

```
podman compose up --exit-code-from serespar && podman compose down
```

The browser runs headless by default, so this needs no X display.

To watch the browser instead, set `SERESPAR_HEADED` and let the container reach
your X server:

```
xhost +local: # unfortunately I couldn't find a tighter permission that works in XWayland
SERESPAR_HEADED=1 podman compose up --exit-code-from serespar && podman compose down
```

`SERESPAR_HEADED` is read by `ResultsParseSession` (see `serespar/parse_session.py`);
any of `1`, `true`, `yes` or `on` turns the window on. The dev parser task sets it
unconditionally, so `parsing/docker` sessions are always headed.
