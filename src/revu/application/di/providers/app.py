from collections.abc import AsyncIterator

from dishka import Provider, Scope, provide

from revu.application.config import load_settings
from revu.application.entities.config import Settings
from revu.application.services.revision_store import ReviewedRevisionStore
from revu.infrastructure.http_client.http_client_gateway import HttpClientGateway


class AppProvider(Provider):
    """Typed configuration and the HTTP transport shared by every connection."""

    scope = Scope.APP

    @provide
    def settings(self) -> Settings:
        """Parse and validate the configuration, failing startup on any error."""
        return load_settings()

    @provide
    async def http_gateway(self, settings: Settings) -> AsyncIterator[HttpClientGateway]:
        """One ``httpx.AsyncClient`` for the whole application.

        Every port and every OpenAI-compatible profile sends through it, and it
        is closed once, when the container shuts down.
        """
        gateway = HttpClientGateway(settings=settings.http)
        try:
            yield gateway
        finally:
            await gateway.aclose()

    @provide
    def reviewed_revisions(self) -> ReviewedRevisionStore:
        """Application-wide: the memory of GitLab's ambiguous update events."""
        return ReviewedRevisionStore()
