"""Sign in with Google on the web (2026-10-12, milestone "Ready for iOS").

The page shows Google's own button (Google Identity Services). Google hands
the page an ID token: a statement, signed by Google, that this browser is
signed in as a given address. The page sends it to `POST /v1/auth/google`;
the server checks the signature against Google's published keys, and that the
token was made for this app (`aud`), by Google (`iss`), is still fresh
(`exp`), and is for an address Google has verified. Only the client id is
needed for that, and it is public: no client secret exists anywhere.

Invite-only (decided 2026-10-12 as the safe default, and reversible): a
verified address is not an account. It is the owner's when it is
`GROCERY_OWNER_EMAIL`, a user's when the owner added it on the People card,
and turned away otherwise.

Switched off until configured: without `GOOGLE_CLIENT_ID` there is no route
and the page shows no button. The demo never has it (it has no accounts).

`verify` is passed in, so no test ever calls Google: the real one is
`google_verifier()`, which uses the `google-auth` library already installed
for Vertex AI.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

__all__ = ["GoogleSignIn", "GoogleUnavailable", "NotSignedIn", "SESSION_DAYS", "configured",
           "google_verifier", "normal_email"]

# How long one sign-in lasts before the page shows the button again: a phone
# should not ask every week, and a lost one should not stay in for ever.
SESSION_DAYS = 90

# Who may have made a Google ID token (Google's documentation names both).
ISSUERS = ("accounts.google.com", "https://accounts.google.com")

# (id token, client id) -> the token's claims. Raises ValueError when the
# token is not one Google signed.
Verifier = Callable[[str, str], Mapping[str, Any]]


class NotSignedIn(ValueError):
    """The token proves nothing: forged, for another app, stale, or for an
    address Google has not verified. A 401."""


class GoogleUnavailable(RuntimeError):
    """Google's keys could not be fetched, so nothing can be checked. A 503."""


def normal_email(email: str) -> str:
    """The form addresses are kept and compared in: trimmed, lower case."""
    return email.strip().lower()


@dataclass(frozen=True)
class GoogleSignIn:
    client_id: str
    owner_email: str | None
    verify: Verifier

    def email(self, credential: str, now: float | None = None) -> str:
        """The verified address `credential` was issued for, or NotSignedIn."""
        return self.identity(credential, now)[0]

    def identity(self, credential: str, now: float | None = None) -> tuple[str, str | None]:
        """The verified address `credential` was issued for and the person's
        first name on Google (else their whole name, else None), or NotSignedIn.

        The library checks the claims too; they are checked again here so
        the rule is in this code, where a test can hold it, whatever verifier
        is passed in.
        """
        try:
            claims = self.verify(credential, self.client_id)
        except ValueError as exc:
            raise NotSignedIn(f"not a valid Google sign-in: {exc}") from exc
        if claims.get("aud") != self.client_id:
            raise NotSignedIn("this Google sign-in was made for another app")
        if claims.get("iss") not in ISSUERS:
            raise NotSignedIn("this sign-in was not made by Google")
        try:
            expires = float(claims["exp"])
        except (KeyError, TypeError, ValueError):
            raise NotSignedIn("this Google sign-in has no end date") from None
        if expires <= (time.time() if now is None else now):
            raise NotSignedIn("this Google sign-in has expired: sign in again")
        email = claims.get("email")
        if not isinstance(email, str) or not email.strip():
            raise NotSignedIn("this Google sign-in carries no address")
        if claims.get("email_verified") not in (True, "true"):
            raise NotSignedIn("Google has not verified this address")
        name = next((str(claims[key]).strip() for key in ("given_name", "name")
                     if str(claims.get(key) or "").strip()), None)
        return normal_email(email), name

    def is_owner(self, email: str) -> bool:
        return self.owner_email is not None and normal_email(email) == self.owner_email


def google_verifier() -> Verifier:
    """The real check: the token's signature against Google's public keys
    (fetched over HTTPS on each sign-in, which is rare), its audience, issuer
    and expiry, by `google.oauth2.id_token.verify_oauth2_token`."""
    from google.auth import exceptions
    from google.auth.transport import requests as transport
    from google.oauth2 import id_token

    request = transport.Request()

    def verify(credential: str, client_id: str) -> Mapping[str, Any]:
        try:
            return id_token.verify_oauth2_token(credential, request, audience=client_id,
                                                clock_skew_in_seconds=10)
        except exceptions.TransportError as exc:
            raise GoogleUnavailable(f"Google's keys could not be fetched: {exc}") from exc
        except (ValueError, exceptions.GoogleAuthError) as exc:
            raise ValueError(str(exc)) from exc

    return verify


def configured(environ: Mapping[str, str] | None = None,
               verify: Verifier | None = None) -> GoogleSignIn | None:
    """Google sign-in as the environment sets it up, or None (off) when
    `GOOGLE_CLIENT_ID` is not set. `GROCERY_OWNER_EMAIL` is the owner's
    Google address; everyone else who signs in is a user."""
    environ = os.environ if environ is None else environ
    client_id = environ.get("GOOGLE_CLIENT_ID", "").strip()
    if not client_id:
        return None
    owner = normal_email(environ.get("GROCERY_OWNER_EMAIL", "")) or None
    return GoogleSignIn(client_id, owner, verify or google_verifier())
