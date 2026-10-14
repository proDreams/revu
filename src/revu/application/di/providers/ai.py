from collections.abc import AsyncIterator

from dishka import Provider, Scope, provide

from revu.application.config import get_settings
from revu.application.entities.enums.webhook_routes_enums import AIProviderEnum
from revu.application.entities.exceptions.webhook_routes_exceptions import (
    AIProviderException,
)
from revu.domain.protocols.ai_provider_protocol import AIProviderProtocol
from revu.infrastructure.ai_providers.gigachat.gigachat_adapter import GigaChatAdapter
from revu.infrastructure.ai_providers.gigachat.gigachat_port import GigaChatPort
from revu.infrastructure.ai_providers.openai.openai_adapter import OpenAIAdapter
from revu.infrastructure.ai_providers.openai.openai_port import OpenAIPort
from revu.infrastructure.ai_providers.openai_compatible.openai_compatible_adapter import (
    OpenAICompatibleAdapter,
)
from revu.infrastructure.ai_providers.openai_compatible.openai_compatible_port import (
    OpenAICompatiblePort,
)
from revu.infrastructure.ai_providers.yandexgpt.yandexgpt_adapter import YandexGPTAdapter
from revu.infrastructure.ai_providers.yandexgpt.yandexgpt_port import YandexGPTPort
from revu.infrastructure.http_client.http_client_gateway import HttpClientGateway


class AIProviderProvider(Provider):
    """The single AI port backed by the configured provider.

    Adapters hold network clients, so they are built once and shared instead of
    being recreated for every webhook. Providers that expose a close hook get it
    called when the container shuts down.
    """

    scope = Scope.APP

    @provide
    async def ai_port(self, http_gateway: HttpClientGateway) -> AsyncIterator[AIProviderProtocol]:
        match get_settings().AI_PROVIDER_CONFIG.AI_PROVIDER:
            case AIProviderEnum.OPENAI:
                yield OpenAIPort(adapter=OpenAIAdapter(http_client=http_gateway))
            case AIProviderEnum.OPENAI_COMPATIBLE:
                yield OpenAICompatiblePort(adapter=OpenAICompatibleAdapter(http_client=http_gateway))
            case AIProviderEnum.GIGACHAT:
                gigachat_adapter = GigaChatAdapter()
                try:
                    yield GigaChatPort(adapter=gigachat_adapter)
                finally:
                    await gigachat_adapter.aclose()
            case AIProviderEnum.YANDEXGPT:
                # The Yandex AI Studio SDK exposes no close hook, so this client
                # has to live for the whole process. Creating it once here still
                # keeps a single connection pool instead of one per webhook.
                yield YandexGPTPort(adapter=YandexGPTAdapter())
            case _:
                raise AIProviderException("Unknown AI provider")
