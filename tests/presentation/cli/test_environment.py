"""Reading what a platform says, without a platform."""

import json

import pytest

from revu.domain.entities.enums.git_provider_enums import GitProviderEnum
from revu.presentation.cli.environment import detect

pytestmark = pytest.mark.unit

GITLAB = {
    "GITLAB_CI": "true",
    "CI_PROJECT_PATH": "group/project",
    "CI_MERGE_REQUEST_IID": "42",
    "CI_MERGE_REQUEST_TITLE": "Add a thing",
    "CI_MERGE_REQUEST_DESCRIPTION": "Why it is needed",
    "CI_MERGE_REQUEST_DIFF_BASE_SHA": "base-sha",
    "CI_COMMIT_SHA": "head-sha",
    "CI_SERVER_URL": "https://gitlab.example.com",
    "CI_JOB_TOKEN": "job-token",
}

GITHUB = {
    "GITHUB_ACTIONS": "true",
    "GITHUB_REPOSITORY": "owner/repo",
    "GITHUB_TOKEN": "gh-token",
    "GITHUB_API_URL": "https://api.github.com",
    "GITHUB_SERVER_URL": "https://github.com",
}


def write_event(tmp_path, payload) -> str:
    path = tmp_path / "event.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    return str(path)


def event_payload(**pull_request) -> dict:
    return {
        "pull_request": {
            "number": 7,
            "title": "Add feature",
            "body": "Implements it",
            "base": {"sha": "base-sha"},
            "head": {"sha": "head-sha"},
            **pull_request,
        }
    }


def test_outside_ci_nothing_is_detected():
    assert detect({}) is None


def test_gitlab_is_read_from_its_own_variables():
    environment = detect(GITLAB)

    assert environment is not None
    assert environment.name == "gitlab"
    assert environment.provider is GitProviderEnum.GITLAB
    assert environment.repo == "group/project"
    assert environment.number == 42
    assert environment.title == "Add a thing"
    assert environment.body == "Why it is needed"
    assert environment.base == "base-sha"
    assert environment.head == "head-sha"
    assert environment.api_url == "https://gitlab.example.com"


def test_a_gitlab_job_token_is_marked_read_only():
    """It can read a merge request and its notes, but it cannot write a note."""
    environment = detect(GITLAB)

    assert environment is not None
    assert environment.token == "job-token"
    assert environment.token_is_read_only is True


def test_a_project_access_token_wins_over_the_job_token():
    environment = detect({**GITLAB, "GIT_PROVIDER_USER_TOKEN": "project-token"})

    assert environment is not None
    assert environment.token == "project-token"
    assert environment.token_is_read_only is False


def test_a_gitlab_run_outside_a_merge_request_has_no_number():
    environment = detect({**GITLAB, "CI_MERGE_REQUEST_IID": ""})

    assert environment is not None
    assert environment.number is None


@pytest.mark.parametrize("value", ["not-a-number", "  "])
def test_a_gitlab_number_that_is_not_a_number_is_ignored(value):
    environment = detect({**GITLAB, "CI_MERGE_REQUEST_IID": value})

    assert environment is not None
    assert environment.number is None


def test_github_reads_the_event_payload(tmp_path):
    environment = detect({**GITHUB, "GITHUB_EVENT_PATH": write_event(tmp_path, event_payload())})

    assert environment is not None
    assert environment.name == "github"
    assert environment.provider is GitProviderEnum.GITHUB
    assert environment.repo == "owner/repo"
    assert (environment.number, environment.title, environment.body) == (7, "Add feature", "Implements it")
    assert (environment.base, environment.head) == ("base-sha", "head-sha")
    assert environment.token == "gh-token"
    assert environment.token_is_read_only is False


def test_github_without_an_event_payload_still_reviews_a_repository(tmp_path):
    """A `workflow_dispatch` run has no pull request; the diff may still be asked for."""
    environment = detect(GITHUB)

    assert environment is not None
    assert environment.number is None
    assert environment.base is None


def test_an_unreadable_event_payload_is_reported_not_fatal(tmp_path, caplog):
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")

    with caplog.at_level("WARNING"):
        environment = detect({**GITHUB, "GITHUB_EVENT_PATH": str(broken)})

    assert environment is not None
    assert environment.number is None
    assert "could not read the CI event payload" in caplog.text


@pytest.mark.parametrize("payload", [[], "text", 42])
def test_an_event_payload_of_the_wrong_shape_is_ignored(tmp_path, payload):
    environment = detect({**GITHUB, "GITHUB_EVENT_PATH": write_event(tmp_path, payload)})

    assert environment is not None
    assert environment.number is None


@pytest.mark.parametrize(
    ("extra", "expected"),
    [
        ({"GITEA_ACTIONS": "true"}, GitProviderEnum.GITEA),
        ({"GITHUB_API_URL": "http://gitea:3000/api/v1"}, GitProviderEnum.GITEA),
        ({"GITHUB_API_URL": "https://ghe.example.com/api/v3"}, GitProviderEnum.GITHUB),
        ({"GITHUB_API_URL": "https://api.github.com"}, GitProviderEnum.GITHUB),
        # An explicit variable is a statement, not a guess.
        ({"GITEA_ACTIONS": "true", "GIT_PROVIDER": "github"}, GitProviderEnum.GITHUB),
    ],
)
def test_github_and_gitea_are_told_apart(extra, expected):
    environment = detect({**GITHUB, **extra})

    assert environment is not None
    assert environment.provider is expected


def test_a_gitea_api_url_is_reduced_to_the_server_root():
    """Gitea's port appends `/api/v1` itself, so handing it back would double it."""
    environment = detect({**GITHUB, "GITHUB_API_URL": "http://gitea:3000/api/v1/"})

    assert environment is not None
    assert environment.name == "gitea"
    assert environment.api_url == "http://gitea:3000"


def test_a_gitea_run_without_an_api_url_falls_back_to_the_server_url():
    environment = detect(
        {
            **GITHUB,
            "GIT_PROVIDER": "gitea",
            "GITHUB_API_URL": "",
            "GITHUB_SERVER_URL": "http://gitea:3000",
        }
    )

    assert environment is not None
    assert environment.api_url == "http://gitea:3000"


def test_the_provider_can_be_named_in_a_variable():
    environment = detect({**GITHUB, "GIT_PROVIDER": "gitea"})

    assert environment is not None
    assert environment.provider is GitProviderEnum.GITEA


def test_an_unknown_provider_variable_is_not_believed():
    environment = detect({**GITHUB, "GIT_PROVIDER": "sourceforge"})

    assert environment is not None
    assert environment.provider is GitProviderEnum.GITHUB
