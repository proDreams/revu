from dishka import Provider, Scope, provide

from revu.application.entities.config import Settings
from revu.application.registry.git_connections import GitConnectionRegistry
from revu.infrastructure.http_client.http_client_gateway import HttpClientGateway


class GitConnectionProvider(Provider):
    """All configured git connections, built once at startup.

    Each connection gets its own port because a port holds credentials and a
    base URL; they share the application HTTP client.
    """

    scope = Scope.APP

    @provide
    def git_connections(self, settings: Settings, http_gateway: HttpClientGateway) -> GitConnectionRegistry:
        return GitConnectionRegistry(settings=settings, http_client=http_gateway)
