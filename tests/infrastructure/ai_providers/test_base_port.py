"""Unit tests for the shared AI-port helpers."""

import pytest

from revu.application.entities.default_prompts import (
    BITBUCKET_INLINE_PROMPT,
    BITBUCKET_RE_REVIEW_PROMPT,
    COMMENT_PROMPT,
    GITEA_INLINE_PROMPT,
    GITEA_RE_REVIEW_PROMPT,
    GITHUB_INLINE_PROMPT,
    GITHUB_RE_REVIEW_PROMPT,
    GITLAB_INLINE_PROMPT,
    GITLAB_RE_REVIEW_PROMPT,
    RE_REVIEW_COMMENT_PROMPT,
)
from revu.application.entities.exceptions.ai_adapters_exceptions import (
    InvalidAIOutput,
    UnknownGitProvider,
)
from revu.application.entities.schemas.ai_providers_schemas.openai_schemas import (
    GithubReviewResponse,
    GitlabReviewResponse,
)
from revu.domain.entities.dto.code_context_dto import (
    CodeContextDTO,
    ContextEntryDTO,
    ContextStatsDTO,
)
from revu.domain.entities.dto.review_context_dto import (
    PreviousCommentDTO,
    ReviewContextDTO,
)
from revu.domain.entities.enums.git_provider_enums import GitProviderEnum
from revu.infrastructure.ai_providers.base import MAX_CONTEXT_FINDINGS, BaseAIPort
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
    assert "PR DATA BEGIN" in prompt and "PR DATA END" in prompt


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


# ── a follow-up review reads differently from a first one ───────────────────

FINDING = PreviousCommentDTO(author="revu-bot", body="импорты лучше построчно", is_revu=True, path="app.py", line=12)
DISCUSSION = PreviousCommentDTO(author="ivan", body="не трогаем этот модуль")


def _context(*comments: PreviousCommentDTO) -> ReviewContextDTO:
    return ReviewContextDTO(comments=comments)


@pytest.mark.parametrize(
    ("git_host", "expected"),
    [
        (GitProviderEnum.GITHUB, GITHUB_RE_REVIEW_PROMPT),
        (GitProviderEnum.GITEA, GITEA_RE_REVIEW_PROMPT),
        (GitProviderEnum.GITLAB, GITLAB_RE_REVIEW_PROMPT),
        (GitProviderEnum.BITBUCKET, BITBUCKET_RE_REVIEW_PROMPT),
    ],
)
def test_get_re_review_prompt_selects_the_host_prompt(git_host, expected):
    assert BaseAIPort._get_re_review_prompt(git_host) == expected


def test_get_re_review_prompt_rejects_an_unknown_host():
    with pytest.raises(UnknownGitProvider):
        BaseAIPort._get_re_review_prompt("unknown")  # type: ignore[arg-type]


def test_a_first_review_uses_the_ordinary_prompt():
    assert BaseAIPort()._inline_instructions(make_task()) == GITHUB_INLINE_PROMPT


def test_a_follow_up_uses_the_re_review_prompt():
    task = make_task(previous_review=_context(FINDING))

    assert BaseAIPort()._inline_instructions(task) == GITHUB_RE_REVIEW_PROMPT


def test_comment_mode_switches_prompt_for_a_follow_up():
    first = BaseAIPort()._comment_instructions(make_task())
    follow_up = BaseAIPort()._comment_instructions(make_task(previous_review=_context(FINDING)))

    assert first == COMMENT_PROMPT
    assert follow_up == RE_REVIEW_COMMENT_PROMPT


def test_a_conversation_without_revu_findings_is_still_a_first_review():
    """There is nothing ReVu said, so there is nothing to verify — but what other
    people said is context for this review like for any other."""
    task = make_task(previous_review=_context(DISCUSSION))

    assert BaseAIPort._is_re_review(task) is False
    assert BaseAIPort()._inline_instructions(task) == GITHUB_INLINE_PROMPT

    rendered = BaseAIPort._render_previous_review(task)
    assert "Pull request discussion" in rendered
    assert "ReVu's earlier findings" not in rendered


def test_other_peoples_comments_reach_the_model_on_a_first_review():
    """Found while testing on GitLab: the notes were fetched and then dropped before
    the prompt, because the renderer asked whether ReVu had findings of its own first.
    """
    task = make_task(previous_review=_context(DISCUSSION))

    prompt = BaseAIPort._get_diff_prompt(task)

    assert "Pull request discussion" in prompt
    assert "не трогаем этот модуль" in prompt


def test_the_system_prompt_still_extends_a_follow_up():
    task = make_task(previous_review=_context(FINDING), system_prompt="Пиши короче")

    assert BaseAIPort()._inline_instructions(task).startswith("Пиши короче\n\n")


def test_the_earlier_findings_travel_in_the_user_message():
    task = make_task(previous_review=_context(FINDING, DISCUSSION))

    prompt = BaseAIPort._get_diff_prompt(task)

    assert "ReVu's earlier findings" in prompt
    assert "1. [не исправлено] app.py:12 — импорты лучше построчно" in prompt
    assert "Pull request discussion" in prompt
    assert "- @ivan: не трогаем этот модуль" in prompt
    # Inside the guarded block, like the diff: a comment is untrusted text too.
    assert prompt.index("=== PR DATA BEGIN ===") < prompt.index("ReVu's earlier findings")
    assert prompt.index("ReVu's earlier findings") < prompt.index("=== PR DATA END ===")


def test_a_finding_the_host_resolved_is_marked_as_such():
    resolved = PreviousCommentDTO(author="revu-bot", body="готово", is_revu=True, resolved=True)

    assert "[помечено как исправленное]" in BaseAIPort._render_previous_review(
        make_task(previous_review=_context(resolved))
    )


def test_a_first_review_message_has_no_extra_sections():
    prompt = BaseAIPort._get_diff_prompt(make_task())

    assert "ReVu's earlier findings" not in prompt
    assert "Pull request discussion" not in prompt


def test_a_comment_body_is_flattened_and_capped():
    """One long comment must not crowd the diff out of the prompt."""
    long_body = "первая строка\n" + "x" * 5000
    finding = PreviousCommentDTO(author="revu-bot", body=long_body, is_revu=True, path="a.py", line=1)

    rendered = BaseAIPort._render_previous_review(make_task(previous_review=_context(finding)))

    assert len(rendered) < 1000
    assert rendered.rstrip().endswith("…")
    # The newline inside the body is flattened into the single finding line.
    assert "\n" not in rendered.split("\n")[1]


def test_only_the_newest_findings_are_shown():
    findings = tuple(
        PreviousCommentDTO(author="revu-bot", body=f"замечание {index}", is_revu=True, path="a.py", line=index)
        for index in range(40)
    )

    rendered = BaseAIPort._render_previous_review(make_task(previous_review=_context(*findings)))

    assert "замечание 39" in rendered
    assert "замечание 14" not in rendered
    assert rendered.count("[не исправлено]") == MAX_CONTEXT_FINDINGS


def test_a_pull_request_without_a_description_says_so():
    prompt = BaseAIPort._get_diff_prompt(make_task(pr_body=None))

    assert "(не указано)" in prompt
    assert "None" not in prompt


def test_free_text_providers_hand_the_finding_status_through():
    """GigaChat and YandexGPT are parsed by hand, so the field travels as JSON."""
    payload = BaseAIPort._parse_inline_payload(
        '{"general_comment": "c", "previous_findings": [{"summary": "s", "status": "fixed"}], "comments": []}',
        provider="test",
        response_model=GithubReviewResponse,
    )

    assert payload["previous_findings"] == [{"summary": "s", "status": "fixed"}]


# ── the surrounding code ────────────────────────────────────────────────────

CODE_CONTEXT = CodeContextDTO(
    entries=(
        ContextEntryDTO(
            kind="symbol", path="src/app/service.py", title="Service.run (строки 1-20)", text="def run(): ..."
        ),
        ContextEntryDTO(
            kind="signature", path="src/app/repo.py", title="Repo.save (сигнатура)", text="def save(self): ..."
        ),
    ),
    stats=ContextStatsDTO(depth="deep", changed_files=1, body_files=1, chars=200),
)


def test_the_surrounding_code_travels_in_the_user_message():
    prompt = BaseAIPort._get_diff_prompt(make_task(code_context=CODE_CONTEXT))

    assert "Surrounding code" in prompt
    assert "[src/app/service.py] Service.run (строки 1-20)" in prompt
    assert "def run(): ..." in prompt
    assert "[src/app/repo.py] Repo.save (сигнатура)" in prompt


def test_the_context_stays_inside_the_guarded_block():
    """Repository code is untrusted text like anything else in a pull request."""
    prompt = BaseAIPort._get_diff_prompt(make_task(code_context=CODE_CONTEXT))

    assert prompt.index("=== PR DATA BEGIN ===") < prompt.index("Surrounding code")
    assert prompt.index("Surrounding code") < prompt.index("=== PR DATA END ===")


def test_the_review_is_told_to_comment_only_on_the_diff():
    prompt = BaseAIPort._get_diff_prompt(make_task(code_context=CODE_CONTEXT))

    assert "Only lines from the diff below may be commented on" in prompt


def test_a_review_without_context_has_no_context_section():
    prompt = BaseAIPort._get_diff_prompt(make_task())

    assert "Surrounding code" not in prompt


def test_an_empty_context_is_not_a_section_either():
    prompt = BaseAIPort._get_diff_prompt(make_task(code_context=CodeContextDTO()))

    assert "Surrounding code" not in prompt


def test_a_truncated_context_admits_it():
    truncated = CodeContextDTO(
        entries=CODE_CONTEXT.entries,
        stats=ContextStatsDTO(depth="deep", chars=200, truncated=True),
    )

    assert "this context is partial" in BaseAIPort._get_diff_prompt(make_task(code_context=truncated))


def test_the_previous_review_and_the_context_can_both_be_present():
    task = make_task(previous_review=_context(FINDING), code_context=CODE_CONTEXT)

    prompt = BaseAIPort._get_diff_prompt(task)

    assert prompt.index("ReVu's earlier findings") < prompt.index("Surrounding code")


@pytest.mark.parametrize(
    "prompt",
    [
        COMMENT_PROMPT,
        GITHUB_INLINE_PROMPT,
        GITEA_INLINE_PROMPT,
        GITLAB_INLINE_PROMPT,
        BITBUCKET_INLINE_PROMPT,
        RE_REVIEW_COMMENT_PROMPT,
        GITHUB_RE_REVIEW_PROMPT,
        GITEA_RE_REVIEW_PROMPT,
        GITLAB_RE_REVIEW_PROMPT,
        BITBUCKET_RE_REVIEW_PROMPT,
    ],
)
def test_every_prompt_asks_for_the_answer_in_russian(prompt):
    """The instructions are English to spend fewer tokens; the review is Russian.

    Dropping this line would silently change the language of every review a person
    reads, so it is a test rather than a convention: the prompts are edited far more
    often than they are read end to end.
    """
    assert "in Russian" in prompt


def test_the_repository_structure_is_rendered_before_the_code():
    task = make_task(code_context=CodeContextDTO(structure="./: pyproject.toml, uv.lock"))

    prompt = BaseAIPort._get_diff_prompt(task)

    assert "Repository structure" in prompt
    assert prompt.index("uv.lock") < prompt.index("Surrounding code")


def test_a_context_of_nothing_but_a_structure_is_not_empty():
    assert CodeContextDTO(structure="./: uv.lock").is_empty is False
