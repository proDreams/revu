"""Configuration validation happens once, at startup, and must fail loudly."""

import pytest
from dynaconf import Dynaconf, ValidationError

from revu.application.config import Config, validate_settings

pytestmark = pytest.mark.unit


def _complete_config(**overrides) -> dict:
    config = {
        "REVIEW_MODE": "inline",
        "GIT_PROVIDER_CONFIG": {
            "GIT_PROVIDER": "gitea",
            "GIT_PROVIDER_USER_TOKEN": "token",
            "GIT_PROVIDER_URL": "https://example.com",
            "GIT_PROVIDER_SECRET_TOKEN": "secret",
        },
        "AI_PROVIDER_CONFIG": {
            "AI_PROVIDER": "openai",
            "AI_PROVIDER_API_KEY": "key",
            "AI_PROVIDER_MODEL": "gpt-4.1-mini",
        },
    }
    config.update(overrides)

    return config


def _patch_settings(monkeypatch, config) -> None:
    monkeypatch.setattr(Config, "settings", Dynaconf(**config))


def test_the_test_fixture_configuration_is_valid(settings):
    """The autouse fixture has to pass validation, otherwise every app test lies."""
    validate_settings()


def test_a_complete_configuration_passes(monkeypatch):
    _patch_settings(monkeypatch, _complete_config())

    validate_settings()


def test_review_mode_is_required(monkeypatch):
    config = _complete_config()
    del config["REVIEW_MODE"]
    _patch_settings(monkeypatch, config)

    with pytest.raises(ValidationError) as exc_info:
        validate_settings()

    assert "REVIEW_MODE" in str(exc_info.value)


def test_unknown_review_mode_is_rejected(monkeypatch):
    _patch_settings(monkeypatch, _complete_config(REVIEW_MODE="Comment"))

    with pytest.raises(ValidationError) as exc_info:
        validate_settings()

    assert "REVIEW_MODE" in str(exc_info.value)


def test_unknown_git_provider_is_rejected(monkeypatch):
    config = _complete_config()
    config["GIT_PROVIDER_CONFIG"]["GIT_PROVIDER"] = "gitlab"
    _patch_settings(monkeypatch, config)

    with pytest.raises(ValidationError) as exc_info:
        validate_settings()

    assert "GIT_PROVIDER" in str(exc_info.value)


def test_an_empty_secret_token_is_rejected(monkeypatch):
    """An empty secret would make every webhook signature forgeable."""
    config = _complete_config()
    config["GIT_PROVIDER_CONFIG"]["GIT_PROVIDER_SECRET_TOKEN"] = ""
    _patch_settings(monkeypatch, config)

    with pytest.raises(ValidationError) as exc_info:
        validate_settings()

    assert "GIT_PROVIDER_SECRET_TOKEN" in str(exc_info.value)


def test_a_missing_user_token_is_rejected(monkeypatch):
    config = _complete_config()
    del config["GIT_PROVIDER_CONFIG"]["GIT_PROVIDER_USER_TOKEN"]
    _patch_settings(monkeypatch, config)

    with pytest.raises(ValidationError) as exc_info:
        validate_settings()

    assert "GIT_PROVIDER_USER_TOKEN" in str(exc_info.value)


def test_gitea_requires_a_base_url(monkeypatch):
    config = _complete_config()
    del config["GIT_PROVIDER_CONFIG"]["GIT_PROVIDER_URL"]
    _patch_settings(monkeypatch, config)

    with pytest.raises(ValidationError) as exc_info:
        validate_settings()

    assert "GIT_PROVIDER_URL" in str(exc_info.value)


def test_github_does_not_require_a_base_url(monkeypatch):
    """github.com has a default API URL; GitHub Enterprise is opt-in."""
    config = _complete_config()
    del config["GIT_PROVIDER_CONFIG"]["GIT_PROVIDER_URL"]
    config["GIT_PROVIDER_CONFIG"]["GIT_PROVIDER"] = "github"
    _patch_settings(monkeypatch, config)

    validate_settings()


def test_unknown_ai_provider_is_rejected(monkeypatch):
    config = _complete_config()
    config["AI_PROVIDER_CONFIG"]["AI_PROVIDER"] = "gemini"
    _patch_settings(monkeypatch, config)

    with pytest.raises(ValidationError) as exc_info:
        validate_settings()

    assert "AI_PROVIDER" in str(exc_info.value)


def test_a_missing_ai_api_key_is_rejected(monkeypatch):
    config = _complete_config()
    del config["AI_PROVIDER_CONFIG"]["AI_PROVIDER_API_KEY"]
    _patch_settings(monkeypatch, config)

    with pytest.raises(ValidationError) as exc_info:
        validate_settings()

    assert "AI_PROVIDER_API_KEY" in str(exc_info.value)


def test_missing_sections_are_reported(monkeypatch):
    _patch_settings(monkeypatch, {"REVIEW_MODE": "inline"})

    with pytest.raises(ValidationError):
        validate_settings()
