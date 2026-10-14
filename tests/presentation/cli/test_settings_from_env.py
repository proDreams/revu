"""A pipeline's whole configuration, built from variables a user knows from the file."""

import pytest

from revu.application.entities.config import ConfigError
from revu.application.entities.enums.context_depth_enums import ContextDepthEnum
from revu.domain.entities.enums.git_provider_enums import GitProviderEnum
from revu.presentation.cli.environment import CiEnvironment
from revu.presentation.cli.settings_from_env import (
    CONNECTION_KEY,
    PROFILE_KEY,
    UNUSED_TOKEN,
    UNUSED_WEBHOOK_SECRET,
    build_settings,
)

pytestmark = pytest.mark.unit

ENVIRONMENT = CiEnvironment(
    name="github",
    provider=GitProviderEnum.GITHUB,
    repo="owner/repo",
    number=7,
    title="Add feature",
    base="base-sha",
    head="head-sha",
    token="gh-token",
)

MINIMAL = {"AI_PROVIDER_API_KEY": "secret", "AI_PROVIDER_MODEL": "gpt-4o-mini"}


def settings_for(env=None):
    return build_settings(ENVIRONMENT, {**MINIMAL, **(env or {})})


def test_one_connection_and_one_profile_are_enough_for_a_pipeline():
    settings = settings_for()

    assert list(settings.git_connections) == [CONNECTION_KEY]
    assert list(settings.ai_profiles) == [PROFILE_KEY]
    assert settings.default_ai_provider == PROFILE_KEY


def test_the_connection_carries_the_host_and_the_platform_token():
    connection = settings_for().git_connections[CONNECTION_KEY]

    assert connection.host is GitProviderEnum.GITHUB
    assert connection.user_token == "gh-token"


def test_the_connection_uses_the_profile_built_here():
    assert settings_for().git_connections[CONNECTION_KEY].ai_provider == PROFILE_KEY


def test_a_webhook_secret_is_filled_in_although_nothing_checks_it():
    """The parser requires one because a server always has one; a pipeline has none."""
    connection = settings_for().git_connections[CONNECTION_KEY]

    assert connection.secret_token == UNUSED_WEBHOOK_SECRET


def test_the_ai_profile_is_built_from_the_environment():
    profile = settings_for(
        {"AI_PROVIDER": "openai_compatible", "AI_PROVIDER_BASE_URL": "https://cheap/v1"}
    ).ai_profiles[PROFILE_KEY]

    assert profile.api_key == "secret"
    assert profile.model == "gpt-4o-mini"
    assert profile.base_url == "https://cheap/v1"


def test_the_ai_vendor_has_a_default():
    assert settings_for().ai_profiles[PROFILE_KEY].vendor.value == "openai"


def test_the_api_url_comes_from_the_detected_environment():
    environment = CiEnvironment(
        name="gitlab",
        provider=GitProviderEnum.GITLAB,
        repo="group/project",
        api_url="https://gitlab.example.com",
    )

    assert build_settings(environment, MINIMAL).git_connections[CONNECTION_KEY].base_url == "https://gitlab.example.com"


def test_an_explicit_url_wins_over_the_detected_one():
    connection = settings_for({"GIT_PROVIDER_URL": "https://elsewhere"}).git_connections[CONNECTION_KEY]

    assert connection.base_url == "https://elsewhere"


def test_the_context_depth_is_passed_through():
    connection = settings_for({"CONTEXT_DEPTH": "deep"}).git_connections[CONNECTION_KEY]

    assert connection.context_depth is ContextDepthEnum.DEEP


def test_the_context_budgets_are_passed_through():
    connection = settings_for({"CONTEXT_MAX_CHARS": "1234"}).git_connections[CONNECTION_KEY]

    assert connection.context_max_chars == 1234


def test_the_default_review_mode_is_the_one_revu_is_built_around():
    """A pipeline that says nothing should not be a configuration error."""
    connection = settings_for().git_connections[CONNECTION_KEY]

    assert connection.review_mode.value == "inline"


def test_the_review_mode_is_passed_through():
    connection = settings_for({"REVIEW_MODE": "comment"}).git_connections[CONNECTION_KEY]

    assert connection.review_mode.value == "comment"


def test_the_log_level_is_passed_through():
    settings = settings_for({"LOG_LEVEL": "DEBUG"})

    assert settings.log.level == "DEBUG"


def test_the_http_client_settings_are_passed_through():
    settings = settings_for({"HTTP_CLIENT_TIMEOUT": "5.5"})

    assert settings.http.timeout == 5.5


@pytest.mark.parametrize("key", ["AI_PROVIDER_API_KEY", "AI_PROVIDER_MODEL"])
def test_a_missing_ai_setting_is_a_configuration_error(key):
    env = {name: value for name, value in MINIMAL.items() if name != key}

    with pytest.raises(ConfigError) as caught:
        build_settings(ENVIRONMENT, env)

    assert key in str(caught.value)


def test_a_run_without_a_token_is_still_configurable():
    """A checkout and a job log need nobody to authenticate as.

    Whether an API is about to be called is the command's business, not the
    configuration's: it is the command that refuses a token-less run which asked for
    a comment or for the host's diff.
    """
    environment = CiEnvironment(name="github", provider=GitProviderEnum.GITHUB, repo="owner/repo")

    connection = build_settings(environment, MINIMAL).git_connections[CONNECTION_KEY]

    assert connection.user_token == UNUSED_TOKEN
