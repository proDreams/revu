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
run_prod: install
	$(MAKE) run
