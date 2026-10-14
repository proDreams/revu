from dataclasses import replace
from unittest.mock import AsyncMock

import pytest

from revu.application.entities.config import (
    AIProfileConfig,
    AppSettings,
    GitConnectionConfig,
    HttpSettings,
    LogSettings,
    Settings,
)
from revu.application.entities.enums.ai_provider_enums import AIProviderEnum
from revu.application.entities.enums.webhook_service_enums import ReviewModeEnum
from revu.application.entities.tenant import GitConnection, TenantContext
from revu.domain.entities.dto.review_task_dto import ReviewTask
from revu.domain.entities.enums.git_provider_enums import GitProviderEnum
from revu.infrastructure.http_client.http_client_gateway import HttpClientGateway

GITHUB_SECRET = "github-secret"
GITEA_SECRET = "gitea-secret"
BITBUCKET_SECRET = "bitbucket-secret"
GITHUB_TOKEN = "github-token"
GITEA_TOKEN = "gitea-token"
BITBUCKET_TOKEN = "bitbucket-token"
GITEA_URL = "https://gitea.internal"
BITBUCKET_URL = "https://bitbucket.internal"


def make_ai_profile(**overrides) -> AIProfileConfig:
    return replace(
        AIProfileConfig(
            name="default",
            vendor=AIProviderEnum.OPENAI,
            api_key="test-key",
            model="gpt-4.1-mini",
        ),
        **overrides,
    )


def make_connection(**overrides) -> GitConnectionConfig:
    return replace(
        GitConnectionConfig(
            key="gh-main",
            host=GitProviderEnum.GITHUB,
            user_token=GITHUB_TOKEN,
            secret_token=GITHUB_SECRET,
            ai_provider="default",
            review_mode=ReviewModeEnum.INLINE,
            max_concurrent_reviews=3,
        ),
        **overrides,
    )


def make_settings(**overrides) -> Settings:
    """A complete configuration with three connections and two AI profiles.

    More than one of each on purpose: multi-tenancy regressions only show up when
    several connections and profiles exist side by side.
    """
    return replace(
        Settings(
            git_connections={
                "gh-main": make_connection(),
                "gitea-int": make_connection(
                    key="gitea-int",
                    host=GitProviderEnum.GITEA,
                    user_token=GITEA_TOKEN,
                    secret_token=GITEA_SECRET,
                    base_url=GITEA_URL,
                    ai_provider="cheap",
                ),
                "bb-client": make_connection(
                    key="bb-client",
                    host=GitProviderEnum.BITBUCKET,
                    user_token=BITBUCKET_TOKEN,
                    secret_token=BITBUCKET_SECRET,
                    base_url=BITBUCKET_URL,
                    reviewer=None,
                ),
            },
            ai_profiles={
                "default": make_ai_profile(),
                "cheap": make_ai_profile(
                    name="cheap",
                    vendor=AIProviderEnum.OPENAI_COMPATIBLE,
                    api_key="cheap-key",
                    model="qwen",
                    base_url="https://cheap.example.com/v1",
                ),
            },
            default_ai_provider="default",
            http=HttpSettings(timeout=30.0, attempts=3, backoff=0.0),
            log=LogSettings(
                directory="logs",
                file="test.log",
                level="DEBUG",
                max_size_mb=10,
                backup_count=5,
            ),
            app=AppSettings(host="0.0.0.0", port=8000),
        ),
        **overrides,
    )


def make_task(**overrides) -> ReviewTask:
    """A review task for the github host, with sensible text."""
    return replace(
        ReviewTask(
            diff="test diff",
            git_host=GitProviderEnum.GITHUB,
            pr_title="test pr title",
            pr_body="test pr body",
        ),
        **overrides,
    )


def make_raw_settings(**overrides) -> dict:
    """The same configuration in its raw (YAML-shaped) form."""
    raw = {
        "REVIEW_MODE": "inline",
        "DEFAULT_AI_PROVIDER": "default",
        "AI_PROVIDERS": {
            "default": {
                "AI_PROVIDER": "openai",
                "AI_PROVIDER_API_KEY": "test-key",
                "AI_PROVIDER_MODEL": "gpt-4.1-mini",
            },
        },
        "GIT_PROVIDERS": {
            "gh-main": {
                "GIT_PROVIDER": "github",
                "GIT_PROVIDER_USER_TOKEN": GITHUB_TOKEN,
                "GIT_PROVIDER_SECRET_TOKEN": GITHUB_SECRET,
            },
        },
        "LOG_DIR": "logs",
        "LOG_FILE": "test.log",
        "LOG_LEVEL": "DEBUG",
        "HTTP_CLIENT_RETRY_BACKOFF": 0.0,
    }
    raw.update(overrides)

    return raw


@pytest.fixture
def ai_profile() -> AIProfileConfig:
    return make_ai_profile()


@pytest.fixture
def git_connection() -> GitConnectionConfig:
    return make_connection()


@pytest.fixture
def http_settings() -> HttpSettings:
    """No retry backoff, so retry tests do not actually wait."""
    return HttpSettings(timeout=30.0, attempts=3, backoff=0.0)


@pytest.fixture
def log_settings() -> LogSettings:
    return LogSettings(directory="logs", file="test.log", level="DEBUG", max_size_mb=10, backup_count=5)


@pytest.fixture
def settings() -> Settings:
    return make_settings()


@pytest.fixture
def app_settings(monkeypatch, settings) -> Settings:
    """Make the DI container build its graph from the typed test settings."""
    monkeypatch.setattr("revu.application.di.providers.app.load_settings", lambda: settings)

    return settings


@pytest.fixture
def make_tenant():
    """Build a tenant context around any connection, with stub ports."""

    def factory(connection: GitConnectionConfig) -> TenantContext:
        return TenantContext(
            connection=GitConnection.build(config=connection, port=AsyncMock()),
            ai_port=AsyncMock(),
        )

    return factory


@pytest.fixture
def tenant(make_tenant, git_connection) -> TenantContext:
    return make_tenant(git_connection)


@pytest.fixture
async def http_gateway(http_settings):
    """A real gateway that is closed after the test instead of leaking."""
    gateway = HttpClientGateway(settings=http_settings)
    try:
        yield gateway
    finally:
        await gateway.aclose()
