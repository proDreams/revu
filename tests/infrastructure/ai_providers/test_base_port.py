"""Unit tests for the shared AI-port helpers."""

import pytest

from revu.application.entities.default_prompts import (
    BITBUCKET_INLINE_PROMPT,
    COMMENT_PROMPT,
    GITEA_INLINE_PROMPT,
    GITHUB_INLINE_PROMPT,
    GITLAB_INLINE_PROMPT,
)
from revu.application.entities.exceptions.ai_adapters_exceptions import (
    InvalidAIOutput,
    UnknownGitProvider,
)
from revu.application.entities.schemas.ai_providers_schemas.openai_schemas import (
    GithubReviewResponse,
    GitlabReviewResponse,
)
from revu.domain.entities.enums.git_provider_enums import GitProviderEnum
from revu.infrastructure.ai_providers.base import BaseAIPort
from tests.conftest import make_task

pytestmark = pytest.mark.unit

VALID_PAYLOAD = '{"general_comment": "c", "comments": [{"path": "p", "line": 1, "side": "RIGHT", "body": "b"}]}'


@pytest.mark.parametrize(
    ("git_host", "expected"),
    [
        (GitProviderEnum.GITHUB, GITHUB_INLINE_PROMPT),
        (GitProviderEnum.GITEA, GITEA_INLINE_PROMPT),
        (GitProviderEnum.GITLAB, GITLAB_INLINE_PROMPT),
        (GitProviderEnum.BITBUCKET, BITBUCKET_INLINE_PROMPT),
    ],
)
def test_get_prompt_selects_the_host_prompt(git_host, expected):
    assert BaseAIPort._get_prompt(git_host) == expected


@pytest.mark.parametrize(
    ("git_host", "expected"),
    [
        (GitProviderEnum.GITHUB, GithubReviewResponse),
        (GitProviderEnum.GITLAB, GitlabReviewResponse),
    ],
)
def test_get_response_model_selects_the_host_model(git_host, expected):
    assert BaseAIPort._get_response_model(git_host) is expected


def test_get_prompt_rejects_an_unknown_host():
    """Unreachable through the configuration, but the guard must still hold."""
    with pytest.raises(UnknownGitProvider):
        BaseAIPort._get_prompt("unknown")  # type: ignore[arg-type]


def test_get_response_model_rejects_an_unknown_host():
    with pytest.raises(UnknownGitProvider):
        BaseAIPort._get_response_model("unknown")  # type: ignore[arg-type]


def test_comment_prompt_is_used_for_comment_mode():
    assert BaseAIPort._get_comment_prompt() == COMMENT_PROMPT


def test_a_system_prompt_extends_the_builtin_prompt():
    instructions = BaseAIPort()._comment_instructions(make_task(system_prompt="extra"))

    assert instructions.startswith("extra\n\n")
    assert COMMENT_PROMPT in instructions


def test_a_blank_system_prompt_is_ignored():
    assert BaseAIPort._with_system_prompt(None, "base") == "base"
    assert BaseAIPort._with_system_prompt("", "base") == "base"


def test_the_diff_prompt_carries_the_task_text():
    prompt = BaseAIPort._get_diff_prompt(make_task(diff="THE DIFF", pr_title="TITLE", pr_body="BODY"))

    assert "TITLE" in prompt
    assert "BODY" in prompt
    assert "THE DIFF" in prompt
    # Untrusted content is delimited so the model treats it as data.
    assert "НАЧАЛО ДАННЫХ PR" in prompt and "КОНЕЦ ДАННЫХ PR" in prompt


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
