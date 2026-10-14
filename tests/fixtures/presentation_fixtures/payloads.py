# The two refs carry different commits on purpose: `fromRef` is the source
# branch and holds the reviewed commits, `toRef` is the target branch. Reading
# the wrong one is then visible in the tests instead of hiding behind equal
# fixture values.
SOURCE_COMMIT_SHA = "1111111111111111111111111111111111111111"
TARGET_COMMIT_SHA = "2222222222222222222222222222222222222222"

VALID_WEBHOOK_PAYLOAD = {
    "action": "opened",
    "pull_request": {
        "number": 12,
        "title": "test2",
        "body": "",
        "head": {"sha": "e0a85d5a2275d8e85cbafcc0ec730e51266c1925"},
    },
    "repository": {"full_name": "CodeOnANapkin/test"},
}

VALID_BITBUCKET_PULL_REQUEST = {
    "id": 42,
    "title": "Add feature X",
    "description": "Implements feature X",
    "reviewers": [
        {
            "user": {
                "name": "bot",
                "emailAddress": "bot@example.com",
                "displayName": "Bot Reviewer",
            }
        },
    ],
    "fromRef": {
        "id": "refs/heads/feature-x",
        "displayId": "feature-x",
        "latestCommit": SOURCE_COMMIT_SHA,
        "repository": {
            "slug": "my-repo",
            "name": "my-repo",
            "project": {"key": "MYPROJ"},
        },
    },
    "toRef": {
        "id": "refs/heads/main",
        "displayId": "main",
        "latestCommit": TARGET_COMMIT_SHA,
        "repository": {
            "slug": "my-repo",
            "name": "my-repo",
            "project": {"key": "MYPROJ"},
        },
    },
}

VALID_BITBUCKET_PAYLOAD = {
    "eventKey": "pr:opened",
    "pullRequest": VALID_BITBUCKET_PULL_REQUEST,
    "repository": {
        "slug": "my-repo",
        "name": "my-repo",
        "project": {"key": "MYPROJ"},
    },
}

INVALID_ACTION_WEBHOOK_PAYLOAD = {
    "action": "invalid_action",
    "pull_request": {
        "number": 12,
        "title": "test2",
        "body": "",
        "head": {"sha": "e0a85d5a2275d8e85cbafcc0ec730e51266c1925"},
    },
    "repository": {"full_name": "CodeOnANapkin/test"},
}

INVALID_WEBHOOK_PAYLOAD = {
    "action": "opened",
    "pull_request": {"title": "test2", "body": "", "head": {"sha": "e0a85d5a2275d8e85cbafcc0ec730e51266c1925"}},
}
