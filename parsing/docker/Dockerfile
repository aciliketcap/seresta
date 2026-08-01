# TODO: this file is WIP and is not working at all!

# You need to make a local playwright python base image by following README.md
FROM playwright:localbuild-noble-20260113-v1.57.0

# TODO: use pwuser, not root !

ADD dist/serespar-0.1.0-py3-none-any.whl /opt

# create uv env
RUN uv venv

# install serespar as a module
RUN source .venv/bin/activate && \
   uv pip install /opt/serespar-0.1.0-py3-none-any.whl

