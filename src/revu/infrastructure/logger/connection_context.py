"""The connection a log record belongs to.

A review runs in a background task, so the connection key cannot live in the
logger name. A context variable set for the task is picked up by a filter and
attached to every record — including the ones emitted by httpx and the SDKs, which
is where a multi-tenant problem usually shows up.
"""

import logging
from contextvars import ContextVar, Token

UNKNOWN_CONNECTION = "-"

_connection_key: ContextVar[str] = ContextVar("connection_key", default=UNKNOWN_CONNECTION)


def set_connection_key(key: str) -> Token[str]:
    """Bind the current task to a connection; returns a token for :func:`reset`."""
    return _connection_key.set(key)


def reset_connection_key(token: Token[str]) -> None:
    """Undo :func:`set_connection_key`, so the value cannot leak into a later task."""
    _connection_key.reset(token)


def get_connection_key() -> str:
    return _connection_key.get()


class ConnectionKeyFilter(logging.Filter):
    """Attach the current connection key to every record that passes through."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.connection_key = get_connection_key()

        return True
