from dishka import Provider, Scope, provide
from fastapi import Request

from revu.application.entities.tenant import TenantContext
from revu.application.registry.ai_profiles import AIProfileRegistry
from revu.application.registry.git_connections import GitConnectionRegistry


class TenantProvider(Provider):
    """Resolves the connection of an incoming webhook for the current request.

    The key comes from the URL path only — never from the request body. That
    ordering matters: the per-connection secret must be known before the body is
    read or trusted.
    """

    scope = Scope.REQUEST

    @provide
    def tenant(
        self,
        request: Request,
        git_connections: GitConnectionRegistry,
        ai_profiles: AIProfileRegistry,
    ) -> TenantContext:
        connection = git_connections.resolve(request.path_params.get("connection_key"))

        return TenantContext(
            connection=connection,
            ai_port=ai_profiles.for_connection(connection.config),
        )
