from collections.abc import AsyncIterator

from dishka import Provider, Scope, provide

from revu.infrastructure.http_client.http_client_gateway import HttpClientGateway


class HttpProvider(Provider):
    """Shared HTTP transport.

    One ``httpx.AsyncClient`` lives for the whole application and is closed
    when the container shuts down, instead of leaking one per webhook.
    """

    scope = Scope.APP

    @provide
    async def http_gateway(self) -> AsyncIterator[HttpClientGateway]:
        gateway = HttpClientGateway()
        try:
            yield gateway
        finally:
            await gateway.aclose()
