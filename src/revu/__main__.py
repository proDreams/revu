"""`python -m revu`, for a checkout that is not installed as a script."""

from revu.presentation.cli.main import main

if __name__ == "__main__":
    raise SystemExit(main())
