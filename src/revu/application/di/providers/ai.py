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

    Adapters hold network clients, so they are built once and shared instead
    of being recreated for every webhook.
    """

    scope = Scope.APP

    @provide
    def ai_port(self, http_gateway: HttpClientGateway) -> AIProviderProtocol:
        match get_settings().AI_PROVIDER_CONFIG.AI_PROVIDER:
            case AIProviderEnum.OPENAI:
                return OpenAIPort(adapter=OpenAIAdapter(http_client=http_gateway))
            case AIProviderEnum.OPENAI_COMPATIBLE:
                return OpenAICompatiblePort(adapter=OpenAICompatibleAdapter(http_client=http_gateway))
            case AIProviderEnum.GIGACHAT:
                return GigaChatPort(adapter=GigaChatAdapter())
            case AIProviderEnum.YANDEXGPT:
                return YandexGPTPort(adapter=YandexGPTAdapter())
            case _:
                raise AIProviderException("Unknown AI provider")
