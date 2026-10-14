from dishka import Provider, Scope, provide

from revu.application.config import get_settings
from revu.application.entities.enums.webhook_routes_enums import GitProviderEnum
from revu.application.entities.exceptions.webhook_routes_exceptions import (
    GitProviderException,
)
from revu.domain.protocols.git_provider_protocol import GitProviderProtocol
from revu.infrastructure.git_providers.bitbucket.bitbucket_port import BitbucketPort
from revu.infrastructure.git_providers.gitea.gitea_port import GiteaPort
from revu.infrastructure.git_providers.github.github_port import GithubPort
from revu.infrastructure.http_client.http_client_gateway import HttpClientGateway


class GitProviderProvider(Provider):
    """Ports that talk to GitHub / Gitea / Bitbucket.

    Everything is stateless and config-driven, so a single instance is shared
    by the whole application.
    """

    scope = Scope.APP

    @provide
    def git_port(self, http_gateway: HttpClientGateway) -> GitProviderProtocol:
        match get_settings().GIT_PROVIDER_CONFIG.GIT_PROVIDER:
            case GitProviderEnum.GITHUB:
                return GithubPort(http_client=http_gateway)
            case GitProviderEnum.GITEA:
                return GiteaPort(http_client=http_gateway)
            case GitProviderEnum.BITBUCKET:
                return BitbucketPort(http_client=http_gateway)
            case _:
                raise GitProviderException("Unknown GIT provider")
