"""One git port per configured connection."""

from revu.application.entities.config import (
    GitConnectionConfig,
    Settings,
    UnknownConnectionError,
)
from revu.application.entities.exceptions.provider_exceptions import (
    GitProviderException,
)
from revu.application.entities.tenant import GitConnection
from revu.domain.entities.enums.git_provider_enums import GitProviderEnum
from revu.domain.protocols.git_provider_protocol import GitProviderProtocol
from revu.infrastructure.git_providers.bitbucket.bitbucket_port import BitbucketPort
from revu.infrastructure.git_providers.gitea.gitea_port import GiteaPort
from revu.infrastructure.git_providers.github.github_port import GithubPort
from revu.infrastructure.http_client.http_client_gateway import HttpClientGateway


def _build_port(config: GitConnectionConfig, http_client: HttpClientGateway) -> GitProviderProtocol:
    match config.host:
        case GitProviderEnum.GITHUB:
            return GithubPort(http_client=http_client, config=config)
        case GitProviderEnum.GITEA:
            return GiteaPort(http_client=http_client, config=config)
        case GitProviderEnum.BITBUCKET:
            return BitbucketPort(http_client=http_client, config=config)
        case _:
            # Unreachable: the configuration validator rejects other hosts.
            raise GitProviderException(f"Unknown GIT provider {config.host!r}")


class GitConnectionRegistry:
    """Resolves a connection key from the webhook URL to its port.

    Every connection gets its own port, because a port carries credentials and a
    base URL. They share the single application HTTP client, which is safe:
    ``httpx.AsyncClient`` supports concurrent use.
    """

    def __init__(self, settings: Settings, http_client: HttpClientGateway) -> None:
        self._connections: dict[str, GitConnection] = {
            key: GitConnection.build(config=config, port=_build_port(config, http_client))
            for key, config in settings.git_connections.items()
        }

    def resolve(self, key: str | None) -> GitConnection:
        connection = self._connections.get(key or "")
        if connection is None:
            raise UnknownConnectionError(f"no git connection configured for key {key!r}")

        return connection

    def keys(self) -> list[str]:
        return sorted(self._connections)

    def hosts(self) -> dict[str, str]:
        """Connection key to host type, for the startup summary (no secrets)."""
        return {key: connection.host.value for key, connection in self._connections.items()}
