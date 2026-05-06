from __future__ import annotations

from typing import Any


_TRANSIENT_ERROR_MARKERS = (
    "connection error",
    "api connection",
    "apiconnectionerror",
    "timeout",
    "timed out",
    "read timeout",
    "rate limit",
    "ratelimiterror",
    "temporarily unavailable",
    "server error",
    "service unavailable",
    "bad gateway",
    "gateway timeout",
    "internal server error",
    "502",
    "503",
    "504",
)


def is_transient_llm_error(error: Any) -> bool:
    message = str(error).lower()
    return any(marker in message for marker in _TRANSIENT_ERROR_MARKERS)
