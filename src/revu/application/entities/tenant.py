"""Per-request composition of one configured git connection."""

import asyncio
from dataclasses import dataclass

from revu.application.entities.config import GitConnectionConfig
from revu.domain.entities.enums.git_provider_enums import GitProviderEnum
from revu.domain.protocols.ai_provider_protocol import AIProviderProtocol
from revu.domain.protocols.git_provider_protocol import GitProviderProtocol


@dataclass(frozen=True, slots=True)
class GitConnection:
    """A configured connection together with its long-lived resources.

    The review budget lives here rather than in the review service so that one
    noisy connection cannot occupy the slots of every other connection.
    """

    config: GitConnectionConfig
    port: GitProviderProtocol
    review_slots: asyncio.Semaphore

    @property
    def key(self) -> str:
        return self.config.key

    @property
    def host(self) -> GitProviderEnum:
        return self.config.host

    @classmethod
    def build(cls, config: GitConnectionConfig, port: GitProviderProtocol) -> "GitConnection":
        return cls(
            config=config,
            port=port,
            review_slots=asyncio.Semaphore(config.max_concurrent_reviews),
        )


@dataclass(frozen=True, slots=True)
class TenantContext:
    """Everything a single webhook needs: one connection and its AI profile."""

    connection: GitConnection
    ai_port: AIProviderProtocol

    @property
    def config(self) -> GitConnectionConfig:
        return self.connection.config

    @property
    def git_port(self) -> GitProviderProtocol:
        return self.connection.port

    @property
    def review_slots(self) -> asyncio.Semaphore:
        return self.connection.review_slots

    @property
    def key(self) -> str:
        return self.connection.key
