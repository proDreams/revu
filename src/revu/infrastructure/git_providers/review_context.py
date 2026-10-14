"""Gathering the comments a pull request already carries, shared by the ports.

Every host exposes this differently, but the shape of the work is the same: walk
a paginated list, map each item, and order the result chronologically so the
prompt can keep the newest ones.
"""

from collections.abc import Callable, Iterable

from revu.domain.entities.dto.review_context_dto import (
    PreviousCommentDTO,
    ReviewContextDTO,
)
from revu.infrastructure.http_client.http_client_gateway import HttpClientGateway

# Bounded on purpose: the prompt keeps only the newest handful of comments, so
# there is nothing to gain from walking a whole discussion.
CONTEXT_PAGE_SIZE = 100
MAX_CONTEXT_PAGES = 3

UrlForPage = Callable[[int], str]
RawComment = dict


async def fetch_list_pages(
    http_client: HttpClientGateway,
    url_for_page: UrlForPage,
    headers: dict[str, str],
) -> list[RawComment]:
    """Every item of a paginated list endpoint, within the page cap.

    A host that answers something unexpected (an error object instead of a list)
    ends the walk with what was collected so far rather than failing the review.
    """
    collected: list[RawComment] = []

    for page in range(1, MAX_CONTEXT_PAGES + 1):
        payload = await http_client.get(url=url_for_page(page), headers=headers)
        items = [item for item in payload if isinstance(item, dict)] if isinstance(payload, list) else []
        collected.extend(items)

        if len(items) < CONTEXT_PAGE_SIZE:
            break

    return collected


def sort_key(raw: RawComment) -> str:
    """A chronological key that needs no date parsing.

    Hosts report ISO-8601 strings (which compare correctly as strings) or epoch
    milliseconds (which compare correctly once zero-padded), and a comment without
    a timestamp simply sorts first.
    """
    for field in ("created_at", "createdAt", "submitted_at", "submittedAt", "createdDate"):
        value = raw.get(field)

        if isinstance(value, str):
            return value

        if isinstance(value, (int, float)):
            return f"{value:020.0f}"

    return ""


def build_context(mapped: Iterable[tuple[str, PreviousCommentDTO | None]]) -> ReviewContextDTO | None:
    """Order the mapped comments by time; ``None`` when the pull request is silent."""
    ordered = [comment for key, comment in sorted(mapped, key=lambda pair: pair[0]) if comment is not None]

    return ReviewContextDTO(comments=tuple(ordered)) if ordered else None


def body_of(raw: RawComment) -> str:
    """Read a comment body, rejecting anything that is not usable text."""
    body = raw.get("body")

    return body if isinstance(body, str) and body.strip() else ""
