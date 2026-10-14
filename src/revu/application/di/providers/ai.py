from collections.abc import AsyncIterator

from dishka import Provider, Scope, provide

from revu.application.entities.config import Settings
from revu.application.registry.ai_profiles import AIProfileRegistry
from revu.infrastructure.http_client.http_client_gateway import HttpClientGateway


class AIProfileProvider(Provider):
    """Every configured AI profile, built once and shared between connections.

    All profiles are constructed eagerly so a misconfigured one fails at startup
    rather than on the first review that uses it. Shutdown closes only the ports
    that own their transport.
    """

    scope = Scope.APP

    @provide
    async def ai_profiles(
        self,
        settings: Settings,
        http_gateway: HttpClientGateway,
    ) -> AsyncIterator[AIProfileRegistry]:
        registry = AIProfileRegistry(settings=settings, http_client=http_gateway)
        try:
            yield registry
        finally:
            await registry.aclose()
