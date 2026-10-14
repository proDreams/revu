from dishka import Provider

from revu.application.di.providers.ai import AIProviderProvider
from revu.application.di.providers.git import GitProviderProvider
from revu.application.di.providers.http import HttpProvider
from revu.application.di.providers.service import WebhookServiceProvider


def get_providers() -> list[Provider]:
    """Return every provider grouped by logical area."""
    return [
        HttpProvider(),
        GitProviderProvider(),
        AIProviderProvider(),
        WebhookServiceProvider(),
    ]


__all__ = ["get_providers"]
