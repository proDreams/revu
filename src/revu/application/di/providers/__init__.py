from dishka import Provider

from revu.application.di.providers.ai import AIProfileProvider
from revu.application.di.providers.app import AppProvider
from revu.application.di.providers.git import GitConnectionProvider
from revu.application.di.providers.service import ReviewServiceProvider
from revu.application.di.providers.tenant import TenantProvider


def get_providers() -> list[Provider]:
    """Return every provider grouped by logical area."""
    return [
        AppProvider(),
        GitConnectionProvider(),
        AIProfileProvider(),
        TenantProvider(),
        ReviewServiceProvider(),
    ]


__all__ = ["get_providers"]
