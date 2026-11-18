import pytest

from claims_ingest.retry import backoff_delay, retry_call


class Flaky:
    def __init__(self, failures: int, error: Exception | None = None) -> None:
        self.failures = failures
        self.error = error or ValueError("temporary")
        self.calls = 0

    def __call__(self) -> str:
        self.calls += 1
        if self.calls <= self.failures:
            raise self.error
        return "done"


def always(_: Exception) -> bool:
    return True


def never(_: Exception) -> bool:
    return False


def test_backoff_doubles_and_respects_the_maximum():
    delays = [backoff_delay(attempt, 2, 10, 0) for attempt in range(1, 5)]

    assert delays == [2, 4, 8, 10]


def test_jitter_adds_at_most_a_quarter_of_the_delay():
    assert backoff_delay(1, 4, 60, 1) == 5


def test_retries_until_the_operation_succeeds():
    operation = Flaky(failures=2)
    waits = []

    result = retry_call(operation, should_retry=always, description="test", sleep=waits.append)

    assert result == "done"
    assert operation.calls == 3
    assert len(waits) == 2
    assert waits[1] > waits[0]


def test_permanent_errors_are_not_retried():
    operation = Flaky(failures=1)
    waits = []

    with pytest.raises(ValueError):
        retry_call(operation, should_retry=never, description="test", sleep=waits.append)

    assert operation.calls == 1
    assert waits == []


def test_last_error_is_raised_when_attempts_run_out():
    operation = Flaky(failures=10)

    with pytest.raises(ValueError, match="temporary"):
        retry_call(
            operation, should_retry=always, description="test", attempts=3, sleep=lambda _: None
        )

    assert operation.calls == 3
