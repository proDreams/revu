FROM python:3.13.7-slim
# Use the official lightweight Python 3.13.7 image as the base.

RUN apt-get update \
    && apt-get install -y --no-install-recommends make curl git \
    && rm -rf /var/lib/apt/lists/*
# Update package lists, install `make`, `curl` and `git`,
# and remove cached apt data to keep the image small.
# `git` is what a CI run reads the change with: the checkout is already on disk,
# so a review in a pipeline asks the forge for nothing.

COPY --from=ghcr.io/astral-sh/uv:0.13.1 /uv /uvx /bin/
# Copy the `uv` and `uvx` executables from the official uv container into /bin.
# Pinned rather than `latest`: uv builds the project itself, so a new uv can change
# how this image builds without a single line here changing — which is exactly what
# happened, from `hatchling` to `uv_build` and back through a version warning.
# Moving this tag means moving the `uv_build` pin in pyproject.toml with it.

WORKDIR /code
# Set the working directory to `/code` inside the container.

COPY pyproject.toml uv.lock README.md /code/
# Copy the project metadata and README into the container.

RUN uv sync --locked --no-install-project
# Install the third-party dependencies exactly as pinned in uv.lock, and nothing
# else. `--no-install-project` is what makes this layer cacheable on the lock alone:
# the project's own source is not here yet, and building it would need
# `src/revu/__init__.py` — which is the error this step used to fail with.

RUN curl -k "https://gu-st.ru/content/lending/russian_trusted_root_ca_pem.crt" \
    -o /tmp/russian_ca.pem \
    && cat /tmp/russian_ca.pem >> "$(uv run python -m certifi)"
# Download the Russian Trusted Root CA certificate. Need for GigaChat integration.

COPY . /code/
# Copy the rest of the application source code into the container.

RUN uv sync --locked
# Install the project itself, now that its source is here. Only this one package is
# built, so the step is quick and the dependencies keep their cached layer.

ENV PATH="/code/.venv/bin:$PATH"
# The console scripts live in the virtual environment `uv sync` created, so `revu`
# works as a command: `docker run ... revu review` in a pipeline.

EXPOSE 8000
# The service listens on port 8000; `docker run` without arguments now works
# because the command is baked into the image as well.

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/health || exit 1

CMD ["make", "run_prod"]
