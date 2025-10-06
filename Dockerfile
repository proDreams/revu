FROM python:3.13.7-slim
# Use the official lightweight Python 3.13.7 image as the base.

RUN apt-get update \
    && apt-get install -y --no-install-recommends make \
    && rm -rf /var/lib/apt/lists/*
# Update package lists, install `make`,
# and remove cached apt data to keep the image small.

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
# Copy the `uv` and `uvx` executables from the latest official uv container
# into /bin, making them available globally in this image.

WORKDIR /code
# Set the working directory to `/code` inside the container.

COPY pyproject.toml uv.lock README.md /code/
# Copy the project metadata and README into the container.

RUN uv sync --locked
# Install the Python dependencies exactly as pinned in uv.lock using uv.
# Creates a virtual environment at `/code/.venv` with reproducible versions.

RUN curl -k "https://gu-st.ru/content/lending/russian_trusted_root_ca_pem.crt" \
    -o /tmp/russian_ca.pem \
    && cat /tmp/russian_ca.pem >> "$(uv run python -m certifi)"
# Download the Russian Trusted Root CA certificate. Need for GigaChat integration.

COPY . /code/
# Copy the rest of the application source code into the container.
