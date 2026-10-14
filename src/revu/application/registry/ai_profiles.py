"""One AI port per configured profile, shared between connections."""

from revu.application.entities.config import (
    AIProfileConfig,
    GitConnectionConfig,
    Settings,
    UnknownConnectionError,
)
from revu.application.entities.enums.ai_provider_enums import AIProviderEnum
from revu.application.entities.exceptions.provider_exceptions import (
    AIProviderException,
)
from revu.domain.protocols.ai_provider_protocol import (
    AIProviderProtocol,
    CloseableAIProvider,
)
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


def _build_port(profile: AIProfileConfig, http_client: HttpClientGateway) -> AIProviderProtocol:
    match profile.vendor:
        case AIProviderEnum.OPENAI:
            return OpenAIPort(adapter=OpenAIAdapter(http_client=http_client, profile=profile))
        case AIProviderEnum.OPENAI_COMPATIBLE:
            return OpenAICompatiblePort(adapter=OpenAICompatibleAdapter(http_client=http_client, profile=profile))
        case AIProviderEnum.GIGACHAT:
            return GigaChatPort(adapter=GigaChatAdapter(profile=profile))
        case AIProviderEnum.YANDEXGPT:
            return YandexGPTPort(adapter=YandexGPTAdapter(profile=profile))
        case _:
            # Unreachable: the configuration validator rejects other vendors.
            raise AIProviderException(f"Unknown AI provider {profile.vendor!r}")


class AIProfileRegistry:
    """Builds every profile once and hands them out by name or by connection.

    All profiles are constructed eagerly so a broken one fails at startup rather
    than on the first review that happens to use it.
    """

    def __init__(self, settings: Settings, http_client: HttpClientGateway) -> None:
        self._profiles: dict[str, AIProviderProtocol] = {
            name: _build_port(profile, http_client) for name, profile in settings.ai_profiles.items()
        }
        self.default_profile = settings.default_ai_provider

    def resolve(self, name: str) -> AIProviderProtocol:
        try:
            return self._profiles[name]
        except KeyError:
            raise UnknownConnectionError(f"no AI profile configured for name {name!r}")

    def for_connection(self, connection: GitConnectionConfig) -> AIProviderProtocol:
        """Resolve the profile of a connection (explicit override or default)."""
        return self.resolve(connection.ai_provider)

    async def aclose(self) -> None:
        """Close only the ports that own their transport (see the protocol docs).

        A profile backed by the shared HTTP client must not be closed here: the
        OpenAI SDK would close that shared client and break every other
        connection.
        """
        for port in self._profiles.values():
            if isinstance(port, CloseableAIProvider):
                await port.aclose()
