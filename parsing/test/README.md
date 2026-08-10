Run test tasks by running the following command in this directory:

```
xhost +local: # unfortunately I couldn't find a thighter permission that works in XWayland
podman compose up --exit-code-from serespar && podman compose down
```
