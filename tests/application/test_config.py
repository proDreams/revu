"""Configuration parsing validates everything once, at startup, and explains itself."""

import logging

import pytest

from revu.application.config import load_log_settings, load_settings
from revu.application.entities.config import (
    DEFAULT_APP_PORT,
    DEFAULT_LOG_DIR,
    DEFAULT_MAX_CONCURRENT_REVIEWS,
    ConfigError,
)
from revu.application.entities.enums.ai_provider_enums import AIProviderEnum
from revu.application.entities.enums.review_mode_enums import ReviewModeEnum
from revu.domain.entities.enums.git_provider_enums import GitProviderEnum
from tests.conftest import GITHUB_SECRET, GITHUB_TOKEN, make_raw_settings

pytestmark = pytest.mark.unit


def _with_connection(**connection) -> dict:
    raw = make_raw_settings()
    raw["GIT_PROVIDERS"] = {"gh-main": {**raw["GIT_PROVIDERS"]["gh-main"], **connection}}

    return raw


def test_a_complete_configuration_is_parsed():
    settings = load_settings(make_raw_settings())

    connection = settings.git_connections["gh-main"]
    assert connection.host == GitProviderEnum.GITHUB
    assert connection.user_token == GITHUB_TOKEN
    assert connection.secret_token == GITHUB_SECRET
    assert connection.ai_provider == "default"
    assert connection.review_mode == ReviewModeEnum.INLINE
    assert connection.max_concurrent_reviews == DEFAULT_MAX_CONCURRENT_REVIEWS
    assert settings.default_ai_provider == "default"
    assert settings.ai_profiles["default"].vendor == AIProviderEnum.OPENAI


def test_the_legacy_format_is_rejected_with_a_migration_hint():
    raw = {"GIT_PROVIDER_CONFIG": {"GIT_PROVIDER": "gitea"}, "AI_PROVIDER_CONFIG": {"AI_PROVIDER": "openai"}}

    with pytest.raises(ConfigError) as exc_info:
        load_settings(raw)

    message = str(exc_info.value)
    assert "was removed in 2.0" in message
    assert "GIT_PROVIDERS" in message and "DEFAULT_AI_PROVIDER" in message


def test_a_configuration_without_providers_names_the_expected_file():
    with pytest.raises(ConfigError) as exc_info:
        load_settings({})

    assert "config/settings.yaml" in str(exc_info.value)
    assert "GIT_PROVIDERS" in str(exc_info.value)


def test_ai_providers_must_not_be_empty():
    with pytest.raises(ConfigError) as exc_info:
        load_settings(make_raw_settings(AI_PROVIDERS={}))

    assert "AI_PROVIDERS" in str(exc_info.value)


@pytest.mark.parametrize("section", ["AI_PROVIDERS", "GIT_PROVIDERS"])
def test_a_section_that_is_not_a_mapping_is_rejected(section):
    with pytest.raises(ConfigError) as exc_info:
        load_settings(make_raw_settings(**{section: "not a mapping"}))

    assert f"{section} must be a mapping" in str(exc_info.value)


def test_a_profile_body_that_is_not_a_mapping_is_rejected():
    with pytest.raises(ConfigError) as exc_info:
        load_settings(make_raw_settings(AI_PROVIDERS={"default": "openai"}))

    assert "AI_PROVIDERS.default must be a mapping" in str(exc_info.value)


def test_git_providers_must_not_be_empty():
    with pytest.raises(ConfigError) as exc_info:
        load_settings(make_raw_settings(GIT_PROVIDERS={}))

    assert "GIT_PROVIDERS" in str(exc_info.value)


def test_a_connection_referencing_an_unknown_profile_is_rejected():
    raw = _with_connection(AI_PROVIDER="cheep")

    with pytest.raises(ConfigError) as exc_info:
        load_settings(raw)

    assert "is not defined in AI_PROVIDERS" in str(exc_info.value)
    assert "known profiles: default" in str(exc_info.value)


def test_an_empty_profile_override_falls_back_to_the_default():
    raw = _with_connection(AI_PROVIDER="")

    assert load_settings(raw).git_connections["gh-main"].ai_provider == "default"


def test_an_unknown_default_profile_is_rejected():
    with pytest.raises(ConfigError) as exc_info:
        load_settings(make_raw_settings(DEFAULT_AI_PROVIDER="nope"))

    assert "DEFAULT_AI_PROVIDER 'nope'" in str(exc_info.value)


def test_the_default_profile_is_required():
    raw = make_raw_settings()
    del raw["DEFAULT_AI_PROVIDER"]

    with pytest.raises(ConfigError) as exc_info:
        load_settings(raw)

    assert "DEFAULT_AI_PROVIDER" in str(exc_info.value)


@pytest.mark.parametrize("key", ["Git-Main", "gh", "gh main", "-gh", "gh.main"])
def test_a_connection_key_that_is_not_url_safe_is_rejected(key):
    raw = make_raw_settings(GIT_PROVIDERS={key: make_raw_settings()["GIT_PROVIDERS"]["gh-main"]})

    with pytest.raises(ConfigError) as exc_info:
        load_settings(raw)

    assert "not a valid connection key" in str(exc_info.value)


@pytest.mark.parametrize("key", ["github", "gh-main", "1st", "client_2"])
def test_url_safe_connection_keys_are_accepted(key):
    raw = make_raw_settings(GIT_PROVIDERS={key: make_raw_settings()["GIT_PROVIDERS"]["gh-main"]})

    assert key in load_settings(raw).git_connections


def test_gitea_requires_a_base_url():
    raw = make_raw_settings(
        GIT_PROVIDERS={
            "gitea-int": {"GIT_PROVIDER": "gitea", "GIT_PROVIDER_USER_TOKEN": "t", "GIT_PROVIDER_SECRET_TOKEN": "s"}
        }
    )

    with pytest.raises(ConfigError) as exc_info:
        load_settings(raw)

    assert "GIT_PROVIDER_URL is required" in str(exc_info.value)


def test_github_does_not_require_a_base_url():
    settings = load_settings(make_raw_settings())

    assert settings.git_connections["gh-main"].base_url is None


def test_github_enterprise_base_url_is_kept():
    raw = _with_connection(GIT_PROVIDER_URL="https://ghe.example.com/api/v3")

    assert load_settings(raw).git_connections["gh-main"].base_url == "https://ghe.example.com/api/v3"


def test_an_unsupported_host_is_rejected():
    raw = _with_connection(GIT_PROVIDER="sourceforge")

    with pytest.raises(ConfigError) as exc_info:
        load_settings(raw)

    assert "must be one of github, gitea, gitlab, bitbucket" in str(exc_info.value)


@pytest.mark.parametrize("key", ["GIT_PROVIDER_USER_TOKEN", "GIT_PROVIDER_SECRET_TOKEN"])
def test_empty_credentials_are_rejected(key):
    raw = _with_connection(**{key: "   "})

    with pytest.raises(ConfigError) as exc_info:
        load_settings(raw)

    assert key in str(exc_info.value)


def test_yandexgpt_requires_a_folder_id():
    raw = make_raw_settings(
        AI_PROVIDERS={"default": {"AI_PROVIDER": "yandexgpt", "AI_PROVIDER_API_KEY": "k", "AI_PROVIDER_MODEL": "m"}}
    )

    with pytest.raises(ConfigError) as exc_info:
        load_settings(raw)

    assert "AI_PROVIDER_FOLDER_ID" in str(exc_info.value)


def test_openai_compatible_requires_a_base_url():
    raw = make_raw_settings(
        AI_PROVIDERS={
            "default": {"AI_PROVIDER": "openai_compatible", "AI_PROVIDER_API_KEY": "k", "AI_PROVIDER_MODEL": "m"}
        }
    )

    with pytest.raises(ConfigError) as exc_info:
        load_settings(raw)

    assert "AI_PROVIDER_BASE_URL" in str(exc_info.value)


def test_an_unknown_ai_vendor_is_rejected():
    raw = make_raw_settings(
        AI_PROVIDERS={"default": {"AI_PROVIDER": "gemini", "AI_PROVIDER_API_KEY": "k", "AI_PROVIDER_MODEL": "m"}}
    )

    with pytest.raises(ConfigError) as exc_info:
        load_settings(raw)

    assert "AI_PROVIDER must be one of" in str(exc_info.value)


def test_an_unknown_review_mode_is_rejected():
    with pytest.raises(ConfigError) as exc_info:
        load_settings(make_raw_settings(REVIEW_MODE="Comment"))

    assert "REVIEW_MODE must be one of comment, inline" in str(exc_info.value)


def test_a_connection_can_override_every_review_setting():
    raw = make_raw_settings(
        REVIEW_MODE="inline",
        SYSTEM_PROMPT="global prompt",
        MAX_CONCURRENT_REVIEWS=5,
    )
    raw["GIT_PROVIDERS"]["gh-main"].update(
        REVIEW_MODE="comment",
        SYSTEM_PROMPT="connection prompt",
        MAX_CONCURRENT_REVIEWS=1,
        AI_PROVIDER="default",
    )

    connection = load_settings(raw).git_connections["gh-main"]

    assert connection.review_mode == ReviewModeEnum.COMMENT
    assert connection.system_prompt == "connection prompt"
    assert connection.max_concurrent_reviews == 1


def test_global_review_settings_are_inherited():
    raw = make_raw_settings(SYSTEM_PROMPT="global prompt", MAX_CONCURRENT_REVIEWS=7)

    connection = load_settings(raw).git_connections["gh-main"]

    assert connection.system_prompt == "global prompt"
    assert connection.max_concurrent_reviews == 7


@pytest.mark.parametrize("value", ["0", "-1", "many"])
def test_an_invalid_concurrency_limit_is_rejected(value):
    raw = _with_connection(MAX_CONCURRENT_REVIEWS=value)

    with pytest.raises(ConfigError) as exc_info:
        load_settings(raw)

    assert "MAX_CONCURRENT_REVIEWS must be a positive integer" in str(exc_info.value)


def test_a_connection_without_an_override_uses_the_default_profile(settings):
    assert settings.ai_profile_for(settings.git_connections["gh-main"]).name == "default"


def test_a_connection_override_selects_another_profile(settings):
    assert settings.ai_profile_for(settings.git_connections["gitea-int"]).name == "cheap"


def test_two_connections_to_the_same_host_and_url_are_reported(caplog):
    """A repository reachable through both would be reviewed twice."""
    raw = make_raw_settings()
    raw["GIT_PROVIDERS"]["gitea-int"] = {
        "GIT_PROVIDER": "github",
        "GIT_PROVIDER_USER_TOKEN": "t",
        "GIT_PROVIDER_SECRET_TOKEN": "s",
    }

    with caplog.at_level(logging.WARNING):
        load_settings(raw)

    assert "same host and base URL" in caplog.text


def test_global_defaults_are_applied():
    settings = load_settings(make_raw_settings())

    assert settings.app.port == DEFAULT_APP_PORT
    assert settings.log.directory == DEFAULT_LOG_DIR
    assert settings.http.attempts == 3


def test_log_settings_never_require_a_file():
    """The logger bootstraps before the configuration is validated."""
    log_settings = load_log_settings({})

    assert log_settings.directory == DEFAULT_LOG_DIR
    assert log_settings.level == "INFO"


def test_failures_are_reported_on_the_pull_request_by_default():
    """A bot that only logs into the void looks like it worked."""
    assert load_settings(make_raw_settings()).git_connections["gh-main"].notify_on_failure is True


def test_the_global_flag_can_turn_reporting_off():
    raw = make_raw_settings(NOTIFY_ON_FAILURE=False)

    assert load_settings(raw).git_connections["gh-main"].notify_on_failure is False


def test_a_connection_can_override_the_flag():
    raw = _with_connection(NOTIFY_ON_FAILURE=True)

    assert load_settings(raw).git_connections["gh-main"].notify_on_failure is True


@pytest.mark.parametrize(
    ("value", "expected"),
    [("false", False), ("no", False), ("off", False), ("TRUE", True), ("yes", True), (True, True), (False, False)],
)
def test_the_flag_accepts_yaml_booleans_and_strings(value, expected):
    raw = _with_connection(NOTIFY_ON_FAILURE=value)

    assert load_settings(raw).git_connections["gh-main"].notify_on_failure is expected


def test_a_non_boolean_flag_is_rejected():
    raw = _with_connection(NOTIFY_ON_FAILURE="maybe")

    with pytest.raises(ConfigError) as exc_info:
        load_settings(raw)

    assert "NOTIFY_ON_FAILURE must be a boolean" in str(exc_info.value)


def test_the_pull_request_discussion_is_included_by_default():
    assert load_settings(make_raw_settings()).git_connections["gh-main"].include_pr_discussion is True


def test_a_connection_can_keep_the_discussion_local():
    """Other people's comments go to the AI provider; a connection may refuse."""
    raw = _with_connection(INCLUDE_PR_DISCUSSION=False)

    assert load_settings(raw).git_connections["gh-main"].include_pr_discussion is False


def test_the_discussion_flag_can_be_turned_off_globally():
    raw = make_raw_settings(INCLUDE_PR_DISCUSSION=False)

    assert load_settings(raw).git_connections["gh-main"].include_pr_discussion is False


def test_a_non_boolean_discussion_flag_is_rejected():
    raw = _with_connection(INCLUDE_PR_DISCUSSION="sometimes")

    with pytest.raises(ConfigError) as exc_info:
        load_settings(raw)

    assert "INCLUDE_PR_DISCUSSION must be a boolean" in str(exc_info.value)
