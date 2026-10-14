from enum import StrEnum


class FindingStatusEnum(StrEnum):
    """Whether a finding from an earlier review still holds."""

    FIXED = "fixed"
    REMAINING = "remaining"


# Models answer in their own words often enough to be worth normalising; anything
# unrecognised counts as remaining, so a review never claims a fix that did not
# happen.
FIXED_ALIASES = frozenset({"fixed", "исправлено", "исправлен", "resolved", "done", "closed"})


def to_finding_status(value: object) -> FindingStatusEnum:
    """Read a status however a model happened to phrase it."""
    return FindingStatusEnum.FIXED if str(value).strip().casefold() in FIXED_ALIASES else FindingStatusEnum.REMAINING
