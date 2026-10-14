from dishka import Provider, Scope, provide

from revu.application.services.webhook_service import WebhookService


class WebhookServiceProvider(Provider):
    """Stateless review orchestrator.

    It holds no provider of its own: the connection and its AI profile arrive
    with each call, so one instance serves every tenant.
    """

    scope = Scope.APP

    @provide
    def webhook_service(self) -> WebhookService:
        return WebhookService()
