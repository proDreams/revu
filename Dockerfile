FROM python:3.13.7-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends make \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /code

COPY pyproject.toml uv.lock README.md /code/
RUN uv sync --locked

COPY . /code/
