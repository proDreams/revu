"""The memory that tells a GitLab title edit apart from a push."""

import pytest

from revu.application.services.revision_store import (
    DEFAULT_REVISION_CAPACITY,
    ReviewedRevisionStore,
)

pytestmark = pytest.mark.unit

FIRST = "1" * 40
SECOND = "2" * 40


def test_a_revision_is_unknown_until_it_is_remembered():
    revisions = ReviewedRevisionStore()

    assert revisions.has_reviewed("gl-self", "group/project", 11, FIRST) is False

    revisions.remember("gl-self", "group/project", 11, FIRST)

    assert revisions.has_reviewed("gl-self", "group/project", 11, FIRST) is True


def test_another_commit_is_a_different_revision():
    revisions = ReviewedRevisionStore()
    revisions.remember("gl-self", "group/project", 11, FIRST)

    assert revisions.has_reviewed("gl-self", "group/project", 11, SECOND) is False


def test_remembering_a_newer_revision_forgets_the_older_one():
    revisions = ReviewedRevisionStore()
    revisions.remember("gl-self", "group/project", 11, FIRST)
    revisions.remember("gl-self", "group/project", 11, SECOND)

    assert revisions.has_reviewed("gl-self", "group/project", 11, FIRST) is False
    assert revisions.has_reviewed("gl-self", "group/project", 11, SECOND) is True


def test_a_different_merge_request_is_a_different_entry():
    revisions = ReviewedRevisionStore()
    revisions.remember("gl-self", "group/project", 11, FIRST)

    assert revisions.has_reviewed("gl-self", "group/project", 12, FIRST) is False


def test_a_different_connection_is_a_different_entry():
    """Two connections can point at the same project with separate histories."""
    revisions = ReviewedRevisionStore()
    revisions.remember("gl-self", "group/project", 11, FIRST)

    assert revisions.has_reviewed("gl-other", "group/project", 11, FIRST) is False


def test_the_store_is_bounded_and_evicts_the_oldest_entry():
    """Eviction costs one redundant review; it can never lose one."""
    revisions = ReviewedRevisionStore(capacity=2)

    revisions.remember("gl-self", "group/project", 1, FIRST)
    revisions.remember("gl-self", "group/project", 2, FIRST)
    revisions.remember("gl-self", "group/project", 3, FIRST)

    assert revisions.has_reviewed("gl-self", "group/project", 1, FIRST) is False
    assert revisions.has_reviewed("gl-self", "group/project", 2, FIRST) is True
    assert revisions.has_reviewed("gl-self", "group/project", 3, FIRST) is True


def test_remembering_an_entry_again_keeps_it_recent():
    revisions = ReviewedRevisionStore(capacity=2)

    revisions.remember("gl-self", "group/project", 1, FIRST)
    revisions.remember("gl-self", "group/project", 2, FIRST)
    revisions.remember("gl-self", "group/project", 1, SECOND)
    revisions.remember("gl-self", "group/project", 3, FIRST)

    assert revisions.has_reviewed("gl-self", "group/project", 1, SECOND) is True
    assert revisions.has_reviewed("gl-self", "group/project", 2, FIRST) is False


def test_the_default_capacity_is_not_tiny():
    assert DEFAULT_REVISION_CAPACITY >= 128
