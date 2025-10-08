import pytest

from revu.application.entities.exceptions.webhook_routes_exceptions import (
    AIProviderException,
    GitProviderException,
)
from revu.application.services.webhook_service import WebhookService
from revu.infrastructure.ai_providers.gigachat.gigachat_port import GigaChatPort
from revu.infrastructure.ai_providers.openai.openai_port import OpenAIPort
from revu.infrastructure.ai_providers.openai_compatible.openai_compatible_port import (
    OpenAICompatiblePort,
)
from revu.infrastructure.ai_providers.yandexgpt.yandexgpt_port import YandexGPTPort
from revu.infrastructure.git_providers.gitea.gitea_port import GiteaPort
from revu.infrastructure.git_providers.github.github_port import GithubPort
from revu.presentation.webhooks.di import (
    get_ai_provider_port,
    get_git_provider_port,
    get_webhook_service,
)


def test_git_provider_github(monkeypatch, settings):
    settings["GIT_PROVIDER_CONFIG"]["GIT_PROVIDER"] = "github"
    monkeypatch.setattr("revu.presentation.webhooks.di.get_settings", lambda: settings)

    port = get_git_provider_port()
    assert isinstance(port, GithubPort)


def test_git_provider_gitea(monkeypatch, settings):
    settings["GIT_PROVIDER_CONFIG"]["GIT_PROVIDER"] = "gitea"
    monkeypatch.setattr("revu.presentation.webhooks.di.get_settings", lambda: settings)

    port = get_git_provider_port()
    assert isinstance(port, GiteaPort)


def test_unknown_git_provider(monkeypatch, settings):
    settings["GIT_PROVIDER_CONFIG"]["GIT_PROVIDER"] = "unknown"
    monkeypatch.setattr("revu.presentation.webhooks.di.get_settings", lambda: settings)

    with pytest.raises(GitProviderException) as exc_info:
        get_git_provider_port()

    assert "Unknown GIT provider" in str(exc_info.value)


def test_ai_provider_openai(monkeypatch, settings):
    settings["AI_PROVIDER_CONFIG"]["AI_PROVIDER"] = "openai"
    monkeypatch.setattr("revu.presentation.webhooks.di.get_settings", lambda: settings)

    port = get_ai_provider_port()
    assert isinstance(port, OpenAIPort)


def test_ai_provider_openai_compatible(monkeypatch, settings):
    settings["AI_PROVIDER_CONFIG"]["AI_PROVIDER"] = "openai_compatible"
    monkeypatch.setattr("revu.presentation.webhooks.di.get_settings", lambda: settings)

    port = get_ai_provider_port()
    assert isinstance(port, OpenAICompatiblePort)


def test_ai_provider_gigachat(monkeypatch, settings):
    settings["AI_PROVIDER_CONFIG"]["AI_PROVIDER"] = "gigachat"
    monkeypatch.setattr("revu.presentation.webhooks.di.get_settings", lambda: settings)
    monkeypatch.setattr("revu.infrastructure.ai_providers.gigachat.gigachat_adapter.get_settings", lambda: settings)

    port = get_ai_provider_port()
    assert isinstance(port, GigaChatPort)


def test_ai_provider_yandexgpt(monkeypatch, settings):
    settings["AI_PROVIDER_CONFIG"]["AI_PROVIDER"] = "yandexgpt"
    monkeypatch.setattr("revu.presentation.webhooks.di.get_settings", lambda: settings)
    monkeypatch.setattr("revu.infrastructure.ai_providers.yandexgpt.yandexgpt_adapter.get_settings", lambda: settings)

    port = get_ai_provider_port()
    assert isinstance(port, YandexGPTPort)


def test_unknown_ai_provider(monkeypatch, settings):
    settings["AI_PROVIDER_CONFIG"]["AI_PROVIDER"] = "unknown"
    monkeypatch.setattr("revu.presentation.webhooks.di.get_settings", lambda: settings)

    with pytest.raises(AIProviderException) as exc_info:
        get_ai_provider_port()

    assert "Unknown AI provider" in str(exc_info.value)


def test_get_webhook_service():
    result = get_webhook_service()

    assert isinstance(result, WebhookService)
