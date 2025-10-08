import pytest
from dynaconf import Dynaconf

import revu.application.config as app_config


@pytest.fixture(autouse=True, scope="session")
def settings():
    fake_settings = Dynaconf(
        GIT_PROVIDER_CONFIG=Dynaconf(
            GIT_PROVIDER="gitea",
            GIT_PROVIDER_USER_TOKEN="test-token",
            GIT_PROVIDER_URL="https://example.com",
            GIT_PROVIDER_SECRET_TOKEN="secret",
        ),
        AI_PROVIDER_CONFIG=Dynaconf(
            AI_PROVIDER="openai",
            AI_PROVIDER_API_KEY="test-key",
            AI_PROVIDER_MODEL="gpt-4.1-mini",
            AI_PROVIDER_SCOPE="test-scope",
            AI_PROVIDER_FOLDER_ID="test-folder-id",
        ),
        REVIEW_MODE="inline",
        LOG_DIR="logs",
        LOG_FILE="test.log",
        LOG_LEVEL="DEBUG",
        MAX_SIZE_MB=10,
        BACKUP_COUNT=5,
    )

    app_config.get_settings = lambda: fake_settings

    return fake_settings
