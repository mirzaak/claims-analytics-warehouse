"""Retry with exponential backoff and jitter."""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable
from typing import TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def backoff_delay(attempt: int, base_delay: float, max_delay: float, jitter: float) -> float:
    """Return the wait after a failed attempt. Attempts are numbered from 1."""
    delay = min(max_delay, base_delay * 2 ** (attempt - 1))
    return delay + delay * 0.25 * jitter


def retry_call(
    operation: Callable[[], T],
    *,
    should_retry: Callable[[Exception], bool],
    description: str,
    attempts: int = 5,
    base_delay: float = 2.0,
    max_delay: float = 60.0,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Run an operation, retrying only the failures that `should_retry` accepts."""
    if attempts < 1:
        raise ValueError("attempts must be at least 1")

    for attempt in range(1, attempts + 1):
        try:
            return operation()
        except Exception as exc:
            if attempt == attempts or not should_retry(exc):
                raise
            delay = backoff_delay(attempt, base_delay, max_delay, random.random())
            logger.warning(
                "retrying operation=%r attempt=%d/%d wait_seconds=%.1f error=%s",
                description,
                attempt,
                attempts,
                delay,
                exc,
            )
            sleep(delay)

    raise AssertionError("retry loop exited without returning")
