"""One call to Gemini through Google's API, shared by everything that asks it.

The callers differ in what they ask (a photo to read, a line to match or
identify) and in what they do with a failure; the transport is the same, and
lives here once. The key is `GEMINI_API_KEY` and is never logged or cached.
"""

from __future__ import annotations

import json
import time
from typing import Any

URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

# A busy or rate-limited answer is tried once more after a pause; a second
# failure in a row, or any other error, is raised.
RETRY_CODES = (429, 500, 503)
RETRY_AFTER_S = 20


class GeminiError(Exception):
    """The call failed, or came back without anything to read."""


def generate(model: str, body: dict[str, Any], api_key: str | None,
             timeout_s: int = 180) -> dict[str, Any]:
    """POST `body` to `model`'s generateContent and return the response JSON."""
    import urllib.error
    import urllib.request

    if not api_key:
        raise GeminiError("GEMINI_API_KEY is not set")
    request = urllib.request.Request(
        URL.format(model=model), data=json.dumps(body).encode(),
        headers={"x-goog-api-key": api_key, "Content-Type": "application/json"})
    for attempt in (1, 2):
        try:
            with urllib.request.urlopen(request, timeout=timeout_s) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            detail = error.read()[:300].decode(errors="replace")
            if attempt == 2 or error.code not in RETRY_CODES:
                raise GeminiError(f"Gemini {error.code}: {detail}") from error
            time.sleep(RETRY_AFTER_S)
    raise GeminiError("unreachable")


def text_of(data: dict[str, Any]) -> str:
    """The answer's text: the first candidate's parts, joined."""
    candidate = (data.get("candidates") or [{}])[0]
    return "".join(part.get("text", "") for part in
                   (candidate.get("content") or {}).get("parts", []))


def finish_reason(data: dict[str, Any]) -> str | None:
    return (data.get("candidates") or [{}])[0].get("finishReason")
