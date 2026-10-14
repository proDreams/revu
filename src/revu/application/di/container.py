from dishka import AsyncContainer, make_async_container
from dishka.integrations.fastapi import FastapiProvider

from revu.application.di.providers import get_providers


def create_container() -> AsyncContainer:
    """Build the application-wide DI graph.

    ``make_async_container`` validates the graph eagerly, so a broken wiring
    fails while the app is being created instead of on the first webhook.
    """
    return make_async_container(*get_providers(), FastapiProvider())
