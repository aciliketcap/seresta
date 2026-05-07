# What do we need a container for?
I'm not exactly sure where playwright installs everything but since it also contains browsers I figured it's better to put everything into a container instead of installing some stuff in a virtual env and some other things in the host OS.

# Which container to use?
I couldn't find a Python based playwright image from Microsoft. The one they provide is for npm and it contains all browsers (which we don't need). So;

1. I build my own Microsoft playwright container image from scratch by using  the original playwright repo. I use the latest date tag for Ubuntu Noble base image and on top of it install only Chromium browser / driver along with playwright.
2. I create app images from this image by adding my scraper code and configuring the persistence layer to save the results.

# How to build playwright base image?
1. I clone the playwright repo and checkout the latest stable release tag
```
git clone git@github.com:microsoft/playwright-python.git
cd playwright-python
git checkout v1.57.0
```
2. Build playwright and browsers via a venv (I use Python 3.9 since the docs say so)
```
uv venv --python 3.9
source .venv/bin/activate
uv pip install -r local-requirements.txt
uv pip install -e .
PLAYWRIGHT_TARGET_WHEEL=manylinux1_x86_64.whl python -m build --wheel
```

3. Copy the [Dockerfile.Dockerfile.my_py_pw_base_image](/docker/Dockerfile.my_py_pw_base_image) from this repo into `utils/docker/`

4. Build our base image as follows: (copied from `utils/docker/build.sh`)
```
cd utils/docker
mkdir dist/
cp ../../dist/*-manylinux*.whl dist/
docker build --platform "linux/amd64" -t "playwright:localbuild-noble-20260113-v1.57.0" -f "Dockerfile.my_py_pw_base_image" .
rm -rf "dist/"
```
5. Optionally you can run tests (with python 3.9) to see if the playwright inside the base image is working properly. However all tests will fail for browsers other than chromium.
```
docker run --rm -it -v $(pwd):/app -w /app playwright:localbuild-noble-20260113-v1.57.0 uv venv --python 3.9 && pip install -r local-requirements.txt && pytest
```
