from dishka import Provider, Scope, provide

from revu.application.services.review_service import ReviewService


class ReviewServiceProvider(Provider):
    """Stateless review orchestrator.

    It holds no provider of its own: the connection and its AI profile arrive
    with each call, so one instance serves every tenant.
    """

    scope = Scope.APP

    @provide
    def review_service(self) -> ReviewService:
        return ReviewService()
