"""Unit tests for the shared AI-port helpers."""

import pytest

from revu.application.entities.default_prompts import (
    BITBUCKET_INLINE_PROMPT,
    COMMENT_PROMPT,
    GITEA_INLINE_PROMPT,
    GITHUB_INLINE_PROMPT,
)
from revu.application.entities.exceptions.ai_adapters_exceptions import (
    InvalidAIOutput,
    UnknownGitProvider,
)
from revu.application.entities.schemas.ai_providers_schemas.openai_schemas import (
    GithubReviewResponse,
)
from revu.infrastructure.ai_providers.base import BaseAIPort

pytestmark = pytest.mark.unit

VALID_PAYLOAD = '{"general_comment": "c", "comments": [{"path": "p", "line": 1, "side": "RIGHT", "body": "b"}]}'


@pytest.mark.parametrize(
    ("git_provider", "expected"),
    [
        ("github", GITHUB_INLINE_PROMPT),
        ("gitea", GITEA_INLINE_PROMPT),
        ("bitbucket", BITBUCKET_INLINE_PROMPT),
    ],
)
def test_get_prompt_selects_the_host_prompt(git_provider, expected):
    assert BaseAIPort._get_prompt(git_provider) == expected


def test_get_prompt_rejects_an_unknown_host():
    with pytest.raises(UnknownGitProvider):
        BaseAIPort._get_prompt("unknown")


def test_comment_prompt_is_used_for_comment_mode():
    assert BaseAIPort._get_comment_prompt() == COMMENT_PROMPT


@pytest.mark.parametrize(
    "raw",
    [
        VALID_PAYLOAD,
        f"```json\n{VALID_PAYLOAD}\n```",
        f"```\n{VALID_PAYLOAD}\n```",
        f"```{VALID_PAYLOAD}```",
        f"```python{VALID_PAYLOAD}",
        f"  {VALID_PAYLOAD}  ",
    ],
)
def test_parse_inline_payload_accepts_json_with_or_without_a_fence(raw):
    parsed = BaseAIPort._parse_inline_payload(raw, provider="test", response_model=GithubReviewResponse)

    assert parsed["general_comment"] == "c"
    assert parsed["comments"] == [{"path": "p", "line": 1, "body": "b", "side": "RIGHT"}]


def test_parse_inline_payload_normalises_the_side_case():
    raw = '{"general_comment": "c", "comments": [{"path": "p", "line": 1, "side": "left", "body": "b"}]}'

    parsed = BaseAIPort._parse_inline_payload(raw, provider="test", response_model=GithubReviewResponse)

    assert parsed["comments"][0]["side"] == "LEFT"


@pytest.mark.parametrize(
    "raw",
    [
        "not json at all",
        "[1, 2, 3]",
        '{"comments": []}',
        '{"general_comment": "c", "comments": [{"path": "p", "body": "b"}]}',
    ],
)
def test_parse_inline_payload_rejects_useless_answers(raw):
    with pytest.raises(InvalidAIOutput):
        BaseAIPort._parse_inline_payload(raw, provider="test", response_model=GithubReviewResponse)
