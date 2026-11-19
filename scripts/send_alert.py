"""Send a pipeline failure alert to a Discord webhook.

Uses only the standard library, so it still works when dependency installation is the
step that failed. Reads FAILED_STEP, RUN_URL, REPOSITORY_URL, TRIGGER, COMMIT_SHA and
DISCORD_WEBHOOK_URL from the environment.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Mapping

RUNBOOK_SECTIONS = {
    "Install": "install",
    "Configure credentials": "configure-credentials",
    "Ingest": "ingest",
    "Install dbt packages": "install-dbt-packages",
    "Source freshness": "source-freshness",
    "dbt build": "dbt-build",
    "Row-count anomaly check": "row-count-anomaly-check",
    "Generate dbt docs": "generate-or-publish-dbt-docs",
    "Publish dbt docs": "generate-or-publish-dbt-docs",
}
USER_AGENT = "claims-analytics-warehouse-alerts/0.1"


def build_message(env: Mapping[str, str]) -> str:
    step = env.get("FAILED_STEP", "").strip() or "unknown step"
    repository = env.get("REPOSITORY_URL", "").rstrip("/")
    section = RUNBOOK_SECTIONS.get(step, "")
    runbook = f"{repository}/blob/main/RUNBOOK.md" + (f"#{section}" if section else "")
    commit = env.get("COMMIT_SHA", "")[:7] or "unknown"
    lines = [
        f"**Claims pipeline failed** at step: **{step}**",
        f"Trigger: {env.get('TRIGGER', 'unknown')} | Commit: {commit}",
        f"Run log: {env.get('RUN_URL', 'unknown')}",
        f"Runbook: {runbook}",
    ]
    return "\n".join(lines)


def post(url: str, message: str, attempts: int = 3) -> None:
    body = json.dumps({"content": message[:2000]}).encode()
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
        method="POST",
    )
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(request, timeout=10):
                return
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt == attempts:
                raise
            print(f"Alert attempt {attempt} failed ({exc}); retrying.", file=sys.stderr)
            time.sleep(2**attempt)


def main() -> int:
    message = build_message(os.environ)
    print(message)
    url = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    if not url:
        print("::warning::DISCORD_WEBHOOK_URL is not set, so the alert was only logged.")
        return 0
    try:
        post(url, message)
    except (urllib.error.URLError, TimeoutError) as exc:
        print(f"::error::Could not send the Discord alert: {exc}")
        return 1
    print("Alert sent to Discord.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
