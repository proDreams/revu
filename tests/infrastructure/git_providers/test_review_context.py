"""Pages and ordering shared by the ports that read a pull request's history."""

from unittest.mock import AsyncMock

import pytest

from revu.domain.entities.dto.review_context_dto import PreviousCommentDTO
from revu.infrastructure.git_providers.review_context import (
    CONTEXT_PAGE_SIZE,
    MAX_CONTEXT_PAGES,
    build_context,
    fetch_list_pages,
    sort_key,
)

pytestmark = pytest.mark.unit


def _page(size: int, start: int = 0) -> list[dict]:
    return [
        {"body": f"comment {index}", "created_at": f"2026-01-01T00:00:{index:02d}Z"} for index in range(start, size)
    ]


async def test_a_short_page_ends_the_walk():
    http_client = AsyncMock()
    http_client.get.return_value = _page(3)

    pages = await fetch_list_pages(http_client, lambda page: f"https://host?page={page}", {})

    assert len(pages) == 3
    assert http_client.get.await_count == 1


async def test_a_full_page_is_followed():
    http_client = AsyncMock()
    http_client.get.side_effect = [_page(CONTEXT_PAGE_SIZE), _page(2)]

    pages = await fetch_list_pages(http_client, lambda page: f"https://host?page={page}", {})

    assert len(pages) == CONTEXT_PAGE_SIZE + 2
    assert http_client.get.await_count == 2
    assert http_client.get.await_args.kwargs["url"].endswith("page=2")


async def test_the_walk_is_capped():
    """A discussion with no end must not turn into an endless request loop."""
    http_client = AsyncMock()
    http_client.get.return_value = _page(CONTEXT_PAGE_SIZE)

    pages = await fetch_list_pages(http_client, lambda page: f"https://host?page={page}", {})

    assert http_client.get.await_count == MAX_CONTEXT_PAGES
    assert len(pages) == CONTEXT_PAGE_SIZE * MAX_CONTEXT_PAGES


@pytest.mark.parametrize("payload", [{"message": "404"}, None, "nonsense", 42])
async def test_a_payload_that_is_not_a_list_ends_the_walk(payload):
    http_client = AsyncMock()
    http_client.get.return_value = payload

    assert await fetch_list_pages(http_client, lambda page: "https://host", {}) == []


async def test_entries_that_are_not_objects_are_skipped():
    http_client = AsyncMock()
    http_client.get.return_value = [{"body": "ok"}, "nonsense", None, 3]

    pages = await fetch_list_pages(http_client, lambda page: "https://host", {})

    assert pages == [{"body": "ok"}]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ({"created_at": "2026-01-02T00:00:00Z"}, "2026-01-02T00:00:00Z"),
        ({"createdAt": "2026-01-03T00:00:00Z"}, "2026-01-03T00:00:00Z"),
        ({"submittedAt": "2026-01-04T00:00:00Z"}, "2026-01-04T00:00:00Z"),
        ({"createdDate": 1_700_000_000_000}, "00000001700000000000"),
        ({}, ""),
        ({"created_at": None}, ""),
    ],
)
def test_a_timestamp_becomes_a_sortable_key(raw, expected):
    assert sort_key(raw) == expected


def test_iso_timestamps_compare_chronologically_as_strings():
    earlier = {"created_at": "2026-01-01T09:00:00Z"}
    later = {"created_at": "2026-01-01T10:00:00Z"}

    assert sort_key(earlier) < sort_key(later)


def test_comments_are_ordered_by_time_and_nones_dropped():
    first = PreviousCommentDTO(author="a", body="first")
    second = PreviousCommentDTO(author="b", body="second")

    context = build_context(
        [
            ("2026-01-02T00:00:00Z", second),
            ("2026-01-01T00:00:00Z", first),
            ("2026-01-03T00:00:00Z", None),
        ]
    )

    assert context is not None
    assert [comment.body for comment in context.comments] == ["first", "second"]


def test_nothing_mapped_is_no_context():
    assert build_context([]) is None
    assert build_context([("2026-01-01T00:00:00Z", None)]) is None
