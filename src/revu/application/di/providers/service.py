from dishka import Provider, Scope, provide

from revu.application.services.webhook_service import WebhookService
from revu.domain.protocols.ai_provider_protocol import AIProviderProtocol
from revu.domain.protocols.git_provider_protocol import GitProviderProtocol


class WebhookServiceProvider(Provider):
    """Application service orchestrating a single review."""

    scope = Scope.APP

    @provide
    def webhook_service(
        self,
        ai_port: AIProviderProtocol,
        git_port: GitProviderProtocol,
    ) -> WebhookService:
        return WebhookService(ai_port=ai_port, git_port=git_port)
