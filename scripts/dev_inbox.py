"""Bring new uploads worth a look into development (`POST /v1/inbox`).

Parham, 2026-10-11: "a trigger so when something new is seen we analyze it
here in the dev". Run when a Claude Code session starts (a SessionStart hook
in .claude/settings.local.json), it asks the live server for uploads not yet
looked at (another person's, a PDF, a failure), saves each file and what was
read from it under data/inbox/ (gitignored: these are people's purchases),
and prints a short list for the session to work through. The server marks
them handed over, so each arrives once.

Silent when there is nothing new, and never fails a session: no network, no
gcloud, a sleeping server that does not wake in time all end in one line.

The server and the owner's password come from GROCERY_URL / GROCERY_TOKEN, or
else from gcloud (the Cloud Run service `grocery`, the secret `grocery-token`).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

INBOX = Path(__file__).resolve().parent.parent / "data" / "inbox"
TIMEOUT_S = 40  # a server that was asleep takes 15-20 s to wake
KEEP_DAYS = 30  # the privacy page's promise for developer copies


def gcloud(*args: str) -> str:
    return subprocess.run(["gcloud", *args], capture_output=True, text=True, check=True,
                          timeout=30).stdout.strip()


def server_and_token() -> tuple[str, str]:
    url = os.environ.get("GROCERY_URL") or gcloud(
        "run", "services", "describe", "grocery", "--region", "europe-west3",
        "--format", "value(status.url)")
    token = os.environ.get("GROCERY_TOKEN") or gcloud(
        "secrets", "versions", "access", "latest", "--secret", "grocery-token")
    return url.rstrip("/"), token


def call(url: str, token: str, method: str = "GET") -> bytes:
    request = urllib.request.Request(url, method=method,
                                     headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
        return response.read()


def summary(item: dict) -> str:
    who = item.get("user") or "the owner"
    read = item.get("read") or []
    what = (f"turned away ({item['turned_away']})" if item.get("turned_away")
            else f"failed: {item.get('error')}" if item["status"] == "failed"
            else f"{len(read)} receipt(s): " + "; ".join(
                f"{r['receipt'].get('store')} {r['receipt'].get('date')} "
                f"{len(r['lines'])} lines" for r in read))
    return f"- {item['kind']} from {who}, {item['created_at'][:16]}: {what}"


def forget_old(now: float | None = None) -> int:
    """Delete the copies older than KEEP_DAYS (owner, 2026-10-15): people's
    uploads stay on the laptop only as long as the privacy page promises.
    Counted from when the copy was saved here."""
    if not INBOX.is_dir():
        return 0
    cutoff = (now or time.time()) - KEEP_DAYS * 86400
    old = [f for f in INBOX.iterdir() if f.is_file() and f.stat().st_mtime < cutoff]
    for f in old:
        f.unlink()
    return len(old)


def main() -> int:
    if forgotten := forget_old():
        print(f"Deleted {forgotten} inbox file(s) older than {KEEP_DAYS} days.")
    try:
        url, token = server_and_token()
        items = json.loads(call(f"{url}/v1/inbox", token, "POST"))
    except Exception as error:  # noqa: BLE001 - never fail a session start
        print(f"Upload inbox not checked: {type(error).__name__}: {error}")
        return 0
    if not items:
        return 0
    INBOX.mkdir(parents=True, exist_ok=True)
    for item in items:
        stem = INBOX / item["job_id"]
        stem.with_suffix(".json").write_text(json.dumps(item, ensure_ascii=False, indent=2),
                                             encoding="utf-8")
        try:
            data = call(f"{url}/v1/inbox/{item['job_id']}/file", token)
            stem.with_suffix(".pdf" if data[:5] == b"%PDF-" else ".jpg").write_bytes(data)
        except Exception as error:  # noqa: BLE001 - the reading alone is still worth a look
            item["kind"] += f" (file not fetched: {error})"
    print(f"{len(items)} new upload(s) to analyze, saved in data/inbox/ (file + what was read):")
    for item in items:
        print(summary(item))
    print("Check each reading against its file; fix the reader where it got something wrong.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
