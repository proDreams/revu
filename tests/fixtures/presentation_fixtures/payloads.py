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
