Run test tasks by running the following command in this directory:

```
podman compose up --exit-code-from serespar && podman compose down
```

The browser runs headless by default for prod and CI automations.

During test development unset the headless mode and let the container reach
your X server:

```
xhost +local: # unfortunately I couldn't find a tighter permission that works in XWayland
SERESPAR_HEADLESS=0 podman compose up --exit-code-from serespar && podman compose down
```
