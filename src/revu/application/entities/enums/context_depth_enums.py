from enum import StrEnum


class ContextDepthEnum(StrEnum):
    """How much surrounding code a review is allowed to read.

    ``flat`` reviews the diff alone, which is predictable and cheap. ``deep`` also
    reads the full bodies of the changed symbols, the signatures of what they call
    and the tests next to them — more useful context, more requests, more tokens,
    and more of the repository leaving the network, which is why it is opt-in.
    """

    FLAT = "flat"
    DEEP = "deep"
