FROM python:3.13.7-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends make curl git \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.13.1 /uv /uvx /bin/

WORKDIR /code

COPY pyproject.toml uv.lock README.md /code/

RUN uv sync --locked --no-install-project

RUN curl -k "https://gu-st.ru/content/lending/russian_trusted_root_ca_pem.crt" \
    -o /tmp/russian_ca.pem \
    && cat /tmp/russian_ca.pem >> "$(uv run python -m certifi)"

COPY . /code/

RUN uv sync --locked

ENV PATH="/code/.venv/bin:$PATH"

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/health || exit 1

CMD ["make", "run_prod"]
