import pytest
from dynaconf import Dynaconf


@pytest.fixture(autouse=True)
def settings(monkeypatch):
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
            AI_PROVIDER_BASE_URL="https://example.com/v1",
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

    monkeypatch.setattr(
        "revu.infrastructure.ai_providers.gigachat.gigachat_adapter.get_settings", lambda: fake_settings
    )
    monkeypatch.setattr("revu.infrastructure.ai_providers.openai.openai_adapter.get_settings", lambda: fake_settings)
    monkeypatch.setattr(
        "revu.infrastructure.ai_providers.openai_compatible.openai_compatible_adapter.get_settings",
        lambda: fake_settings,
    )
    monkeypatch.setattr(
        "revu.infrastructure.ai_providers.yandexgpt.yandexgpt_adapter.get_settings", lambda: fake_settings
    )
    monkeypatch.setattr("revu.presentation.webhooks.di.get_settings", lambda: fake_settings)
    monkeypatch.setattr("revu.presentation.webhooks.validators.get_settings", lambda: fake_settings)
    monkeypatch.setattr("revu.infrastructure.git_providers.gitea.gitea_port.get_settings", lambda: fake_settings)
    monkeypatch.setattr("revu.infrastructure.git_providers.github.github_port.get_settings", lambda: fake_settings)
    monketpatch.setattr("revu.infrastructure.git_providers.bitbucket.bitbucket_port.get_settings", lambda: fake_settings)

    return fake_settings
