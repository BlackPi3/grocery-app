"""One call to Gemini through Google's API, shared by everything that asks it.

The callers differ in what they ask (a photo to read, a line to match or
identify) and in what they do with a failure; the transport is the same, and
lives here once.

Two doors to the same models, chosen by the environment:

- **Vertex AI**, when `GEMINI_VERTEX_PROJECT` names a Google Cloud project.
  The call signs in as whoever Application Default Credentials say: the
  server's service account on Cloud Run, `gcloud auth application-default
  login` on the laptop. No key. It is billed to that project, so the trial
  credit pays for it (Parham, 2026-10-03), where the AI Studio API is no
  longer covered by trial credit.
- **The Gemini API** (AI Studio) with `GEMINI_API_KEY`, paid on its own bill.

An explicit `api_key` argument always means the Gemini API. Neither the key
nor a token is ever logged or cached.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
# The global endpoint: the Flash models are not offered in europe-west3 or
# europe-west4 (tried 2026-10-03).
VERTEX_URL = ("https://aiplatform.googleapis.com/v1/projects/{project}/locations/global/"
              "publishers/google/models/{model}:generateContent")
VERTEX_ENV = "GEMINI_VERTEX_PROJECT"
KEY_ENV = "GEMINI_API_KEY"

# A busy or rate-limited answer is tried once more after a pause; a second
# failure in a row, or any other error, is raised.
RETRY_CODES = (429, 500, 503)
RETRY_AFTER_S = 20


class GeminiError(Exception):
    """The call failed, or came back without anything to read."""


def configured() -> bool:
    """Is there a way in: a Vertex project or a Gemini API key?"""
    return bool(os.environ.get(VERTEX_ENV) or os.environ.get(KEY_ENV))


NOT_CONFIGURED = f"neither {VERTEX_ENV} nor {KEY_ENV} is set"

_credentials: Any = None


def vertex_token() -> str:
    """An access token from Application Default Credentials, refreshed when stale."""
    global _credentials
    import google.auth
    import google.auth.transport.requests

    if _credentials is None:
        _credentials, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"])
    if not _credentials.valid:
        _credentials.refresh(google.auth.transport.requests.Request())
    return _credentials.token


def endpoint(model: str, api_key: str | None = None) -> tuple[str, dict[str, str]]:
    """Where to send a call for `model`, and how to sign it."""
    if api_key:
        return URL.format(model=model), {"x-goog-api-key": api_key}
    if project := os.environ.get(VERTEX_ENV):
        return (VERTEX_URL.format(project=project, model=model),
                {"Authorization": f"Bearer {vertex_token()}"})
    if key := os.environ.get(KEY_ENV):
        return URL.format(model=model), {"x-goog-api-key": key}
    raise GeminiError(NOT_CONFIGURED)


def generate(model: str, body: dict[str, Any], api_key: str | None = None,
             timeout_s: int = 180) -> dict[str, Any]:
    """POST `body` to `model`'s generateContent and return the response JSON."""
    import urllib.error
    import urllib.request

    url, auth = endpoint(model, api_key)
    # The Gemini API takes a message with no role as the user's; Vertex
    # refuses it ("Please use a valid role"), so it is said for both.
    body = {**body, "contents": [{"role": "user", **content}
                                 for content in body.get("contents", [])]}
    request = urllib.request.Request(
        url, data=json.dumps(body).encode(),
        headers={**auth, "Content-Type": "application/json"})
    for attempt in (1, 2):
        try:
            with urllib.request.urlopen(request, timeout=timeout_s) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            detail = error.read()[:300].decode(errors="replace")
            if attempt == 2 or error.code not in RETRY_CODES:
                raise GeminiError(f"Gemini {error.code}: {detail}") from error
            time.sleep(RETRY_AFTER_S)
        except (TimeoutError, urllib.error.URLError) as error:
            # 2026-10-09: a read that timed out escaped as a bare TimeoutError
            # and ended a whole batch run, twice in one day. It is tried once
            # more, then it is a Gemini failure like any other.
            if attempt == 2:
                raise GeminiError(f"Gemini did not answer: {error}") from error
            time.sleep(RETRY_AFTER_S)
    raise GeminiError("unreachable")


def text_of(data: dict[str, Any]) -> str:
    """The answer's text: the first candidate's parts, joined."""
    candidate = (data.get("candidates") or [{}])[0]
    return "".join(part.get("text", "") for part in
                   (candidate.get("content") or {}).get("parts", []))


def finish_reason(data: dict[str, Any]) -> str | None:
    return (data.get("candidates") or [{}])[0].get("finishReason")
