from dataclasses import dataclass

from revu.domain.entities.enums.git_provider_enums import GitProviderEnum


@dataclass(frozen=True, slots=True)
class ReviewTask:
    """Everything one review needs, independent of any provider instance.

    It is a value object on purpose: an AI port is shared between git
    connections, so the prompt and the host-specific output format travel with
    the task instead of being baked into the port.
    """

    diff: str
    git_host: GitProviderEnum
    pr_title: str
    pr_body: str | None = None
    system_prompt: str | None = None
