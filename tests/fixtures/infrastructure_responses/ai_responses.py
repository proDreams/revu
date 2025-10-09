VALID_GITHUB_AI_RESPONSE_JSON = """{
    "general_comment": "test comment",
    "comments": [
        {"path": "test path", "position": 0, "body": "test body"},
        {"path": "test path2", "position": 5, "body": "test body 2"}
    ]
}
"""

VALID_GITEA_AI_RESPONSE_JSON = """{
    "general_comment": "test comment",
    "comments": [
        {"path": "test path", "old_position": 0, "new_position": 5, "body": "test body"},
        {"path": "test path2", "old_position": 5, "new_position": 0, "body": "test body 2"}
    ]
}
"""

VALID_GITEA_MARKDOWN_AI_RESPONSE_JSON = """```
{
    "general_comment": "test comment",
    "comments": [
        {"path": "test path", "old_position": 0, "new_position": 5, "body": "test body"},
        {"path": "test path2", "old_position": 5, "new_position": 0, "body": "test body 2"}
    ]
}
```"""
