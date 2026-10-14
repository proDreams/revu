# COMMON
install:
	uv sync

lint:
	uv run pre-commit run --all


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
