VALID_GITHUB_AI_RESPONSE_JSON = """{
    "general_comment": "test comment",
    "comments": [
        {"path": "test path", "line": 0, "side": "RIGHT", "body": "test body"},
        {"path": "test path2", "line": 5, "side": "LEFT", "body": "test body 2"}
    ]
}
"""

# Providers without schema enforcement may answer in a different case; the
# schema normalises `side` instead of failing the whole review.
VALID_GITHUB_AI_RESPONSE_JSON_LOWERCASE_SIDE = """{
    "general_comment": "test comment",
    "comments": [
        {"path": "test path", "line": 3, "side": "left", "body": "test body"}
    ]
}
"""

VALID_BITBUCKET_AI_RESPONSE_JSON = """{
    "general_comment": "test comment",
    "comments": [
        {"path": "test path", "line": 0, "lineType": "ADDED", "body": "test body"},
        {"path": "test path2", "line": 5, "lineType": "REMOVED", "body": "test body 2"}
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

# Valid JSON that does not match the review schema: the comment has no anchor.
INCOMPLETE_AI_RESPONSE_JSON = """{
    "general_comment": "test comment",
    "comments": [{"path": "test path", "body": "test body"}]
}
"""

# No `general_comment` key at all.
MISSING_GENERAL_COMMENT_AI_RESPONSE_JSON = """{
    "comments": []
}
"""

# A JSON value that is not an object.
AI_RESPONSE_JSON_ARRAY = """[1, 2, 3]"""
