"""Reading repository files, shared by the ports.

The context modes need more than a diff: the body of a changed symbol, the
signature of something it calls, the test next to it. Every host exposes that over
its own endpoints, but the shape of the work — list the tree once, then read the few
files that matter — is the same.
"""

#: A monorepo cannot be listed entirely: the tree call is one request and its
#: response is held in memory, so the walk stops well before anything pathological.
MAX_TREE_ENTRIES = 20_000

#: A file larger than this is generated or data, never the code under review.
MAX_FILE_CHARS = 200_000


def decode(content: object) -> str:
    """Decode a raw HTTP body, tolerating an encoding the host got wrong."""
    if isinstance(content, bytes):
        return content.decode("utf-8", errors="replace")

    return content if isinstance(content, str) else ""


def too_large(text: str) -> bool:
    """Whether a file is past the size a review should carry."""
    return len(text) > MAX_FILE_CHARS
