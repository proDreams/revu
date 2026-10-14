# COMMON
install:
	uv sync

lint:
	uv run pre-commit run --all

# The pre-commit hook cannot see the project dependencies, so it misses type
# errors at the fastapi/pydantic/openai boundary; this one does not.
typecheck:
	uv run mypy src


# DEV
install_dev:
	uv sync --all-extras
	uv run pre-commit install

run:
	uv run app

# PROD
# `--frozen --no-sync` reuses the environment baked into the image at build
# time. The previous `run_prod: install` re-resolved dependencies (without
# --frozen) and needed the network on every container start.
run_prod:
	uv run --frozen --no-sync app
