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

VALID_BITBUCKET_PAYLOAD = {
    "eventKey": "pr:opened",
    "pullRequest": {
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
            "latestCommit": "e0a85d5a2275d8e85cbafcc0ec730e51266c1925",
            "repository": {
                "slug": "my-repo",
                "name": "my-repo",
                "project": {"key": "MYPROJ"},
            },
        },
        "toRef": {
            "id": "refs/heads/main",
            "displayId": "main",
            "latestCommit": "e0a85d5a2275d8e85cbafcc0ec730e51266c1925",
            "repository": {
                "slug": "my-repo",
                "name": "my-repo",
                "project": {"key": "MYPROJ"},
            },
        },
    },
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
