from revu.application.config import get_settings
from revu.application.entities.enums.webhook_routes_enums import (
    AIProviderEnum,
    GitProviderEnum,
)
from revu.application.entities.exceptions.webhook_routes_exceptions import (
    AIProviderException,
    GitProviderException,
)
from revu.application.services.webhook_service import WebhookService
from revu.infrastructure.ai_providers.openai.openai_port import (
    OpenAIPort,
    get_openai_port,
)
from revu.infrastructure.ai_providers.openai_compatible.openai_compatible_port import (
    OpenAICompatiblePort,
    get_openai_compatible_port,
)
from revu.infrastructure.git_providers.gitea.gitea_port import (
    GiteaPort,
    get_gitea_port,
)
from revu.infrastructure.git_providers.github.github_port import (
    GithubPort,
    get_github_port,
)


def get_git_provider_port() -> GithubPort | GiteaPort:
    match get_settings().GIT_PROVIDER_CONFIG.GIT_PROVIDER:
        case GitProviderEnum.GITHUB:
            return get_github_port()
        case GitProviderEnum.GITEA:
            return get_gitea_port()
        case _:
            raise GitProviderException("Unknown GIT provider")


def get_ai_provider_port() -> OpenAIPort | OpenAICompatiblePort:
    match get_settings().AI_PROVIDER_CONFIG.AI_PROVIDER:
        case AIProviderEnum.OPENAI:
            return get_openai_port()
        case AIProviderEnum.OPENAI_COMPATIBLE:
            return get_openai_compatible_port()
        case _:
            raise AIProviderException("Unknown AI provider")


def get_webhook_service():
    return WebhookService(git_port=get_git_provider_port(), ai_port=get_ai_provider_port())
