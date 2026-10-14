import pytest
from dynaconf import Dynaconf

from revu.application.config import Config
from revu.infrastructure.http_client.http_client_gateway import HttpClientGateway


@pytest.fixture(autouse=True)
def settings(monkeypatch):
    # Nested sections are plain dicts on purpose: that is what Dynaconf builds
    # from the YAML settings file, and only that shape supports the dotted
    # lookups used by validate_settings() (a nested Dynaconf raises
    # "Invalid dotted lookup").
    fake_settings = Dynaconf(
        GIT_PROVIDER_CONFIG={
            "GIT_PROVIDER": "gitea",
            "GIT_PROVIDER_USER_TOKEN": "test-token",
            "GIT_PROVIDER_URL": "https://example.com",
            "GIT_PROVIDER_SECRET_TOKEN": "secret",
            "GIT_PROVIDER_REVIEWER": "bot",
        },
        AI_PROVIDER_CONFIG={
            "AI_PROVIDER": "openai",
            "AI_PROVIDER_API_KEY": "test-key",
            "AI_PROVIDER_BASE_URL": "https://example.com/v1",
            "AI_PROVIDER_MODEL": "gpt-4.1-mini",
            "AI_PROVIDER_SCOPE": "test-scope",
            "AI_PROVIDER_FOLDER_ID": "test-folder-id",
        },
        REVIEW_MODE="inline",
        SYSTEM_PROMPT=None,
        HTTP_CLIENT_TIMEOUT=30.0,
        HTTP_CLIENT_REQUEST_ATTEMPTS=3,
        HTTP_CLIENT_RETRY_BACKOFF=0.0,
        MAX_CONCURRENT_REVIEWS=3,
        LOG_DIR="logs",
        LOG_FILE="test.log",
        LOG_LEVEL="DEBUG",
        MAX_SIZE_MB=10,
        BACKUP_COUNT=5,
    )

    # Every module goes through get_settings(), which returns Config.settings;
    # patching it once keeps the whole application on the same fake config
    # instead of hand-listing the modules that happened to import it.
    monkeypatch.setattr(Config, "settings", fake_settings)

    return fake_settings


@pytest.fixture
async def http_gateway(settings):
    """A real gateway that is closed after the test instead of leaking."""
    gateway = HttpClientGateway()
    try:
        yield gateway
    finally:
        await gateway.aclose()
