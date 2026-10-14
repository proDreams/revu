import pytest

from revu.application.di import create_container
from revu.application.entities.exceptions.webhook_routes_exceptions import (
    AIProviderException,
    GitProviderException,
)
from revu.application.services.webhook_service import WebhookService
from revu.domain.protocols.ai_provider_protocol import AIProviderProtocol
from revu.domain.protocols.git_provider_protocol import GitProviderProtocol
from revu.infrastructure.ai_providers.gigachat.gigachat_port import GigaChatPort
from revu.infrastructure.ai_providers.openai.openai_port import OpenAIPort
from revu.infrastructure.ai_providers.openai_compatible.openai_compatible_port import (
    OpenAICompatiblePort,
)
from revu.infrastructure.ai_providers.yandexgpt.yandexgpt_port import YandexGPTPort
from revu.infrastructure.git_providers.bitbucket.bitbucket_port import BitbucketPort
from revu.infrastructure.git_providers.gitea.gitea_port import GiteaPort
from revu.infrastructure.git_providers.github.github_port import GithubPort
from revu.infrastructure.http_client.http_client_gateway import HttpClientGateway

pytestmark = pytest.mark.unit


async def test_git_provider_github(settings):
    settings["GIT_PROVIDER_CONFIG"]["GIT_PROVIDER"] = "github"

    async with create_container() as container:
        assert isinstance(await container.get(GitProviderProtocol), GithubPort)


async def test_git_provider_gitea(settings):
    settings["GIT_PROVIDER_CONFIG"]["GIT_PROVIDER"] = "gitea"

    async with create_container() as container:
        assert isinstance(await container.get(GitProviderProtocol), GiteaPort)


async def test_git_provider_bitbucket(settings):
    settings["GIT_PROVIDER_CONFIG"]["GIT_PROVIDER"] = "bitbucket"

    async with create_container() as container:
        assert isinstance(await container.get(GitProviderProtocol), BitbucketPort)


async def test_unknown_git_provider(settings):
    settings["GIT_PROVIDER_CONFIG"]["GIT_PROVIDER"] = "unknown"

    async with create_container() as container:
        with pytest.raises(GitProviderException) as exc_info:
            await container.get(GitProviderProtocol)

    assert "Unknown GIT provider" in str(exc_info.value)


async def test_ai_provider_openai(settings):
    settings["AI_PROVIDER_CONFIG"]["AI_PROVIDER"] = "openai"

    async with create_container() as container:
        assert isinstance(await container.get(AIProviderProtocol), OpenAIPort)


async def test_ai_provider_openai_compatible(settings):
    settings["AI_PROVIDER_CONFIG"]["AI_PROVIDER"] = "openai_compatible"

    async with create_container() as container:
        assert isinstance(await container.get(AIProviderProtocol), OpenAICompatiblePort)


async def test_ai_provider_gigachat(settings):
    settings["AI_PROVIDER_CONFIG"]["AI_PROVIDER"] = "gigachat"

    async with create_container() as container:
        assert isinstance(await container.get(AIProviderProtocol), GigaChatPort)


async def test_ai_provider_yandexgpt(settings):
    settings["AI_PROVIDER_CONFIG"]["AI_PROVIDER"] = "yandexgpt"

    async with create_container() as container:
        assert isinstance(await container.get(AIProviderProtocol), YandexGPTPort)


async def test_unknown_ai_provider(settings):
    settings["AI_PROVIDER_CONFIG"]["AI_PROVIDER"] = "unknown"

    async with create_container() as container:
        with pytest.raises(AIProviderException) as exc_info:
            await container.get(AIProviderProtocol)

    assert "Unknown AI provider" in str(exc_info.value)


async def test_webhook_service_is_wired(settings):
    async with create_container() as container:
        service = await container.get(WebhookService)

    assert isinstance(service, WebhookService)


async def test_gateway_is_created_once_and_shared(settings):
    async with create_container() as container:
        first = await container.get(HttpClientGateway)
        second = await container.get(HttpClientGateway)

    assert first is second


async def test_gateway_closes_http_client_on_container_close(settings):
    async with create_container() as container:
        gateway = await container.get(HttpClientGateway)
        assert gateway._client.is_closed is False

    assert gateway._client.is_closed is True
