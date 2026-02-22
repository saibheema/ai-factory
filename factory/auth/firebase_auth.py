"""Firebase Authentication middleware for FastAPI.

Usage in routes::

    from factory.auth.firebase_auth import get_current_user, AuthUser

    @app.get("/api/me")
    def me(user: AuthUser = Depends(get_current_user)):
        return {"uid": user.uid, "email": user.email}
"""

import os
from dataclasses import dataclass

import firebase_admin  # type: ignore
from firebase_admin import auth, credentials  # type: ignore
from fastapi import HTTPException, Request


@dataclass
class AuthUser:
    uid: str
    email: str
    display_name: str


# ── singleton init ───────────────────────────────────────────
_initialised = False


def _ensure_firebase() -> None:
    global _initialised
    if _initialised:
        return
    # Cloud Run → Application Default Credentials (auto)
    # Local dev → set GOOGLE_APPLICATION_CREDENTIALS env var
    cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if cred_path:
        cred = credentials.Certificate(cred_path)
    else:
        cred = credentials.ApplicationDefault()
    firebase_admin.initialize_app(cred, {
        "projectId": os.getenv("GCP_PROJECT_ID", "unicon-494419"),
    })
    _initialised = True


def verify_token(id_token: str) -> AuthUser:
    """Verify a Firebase ID token and return the AuthUser."""
    _ensure_firebase()
    decoded = auth.verify_id_token(id_token)
    return AuthUser(
        uid=decoded["uid"],
        email=decoded.get("email", ""),
        display_name=decoded.get("name", decoded.get("email", "")),
    )


# ── FastAPI dependency ───────────────────────────────────────
def get_current_user(request: Request) -> AuthUser:
    """Extract and verify Firebase token from Authorization header.

    Raises HTTP 401 if missing / invalid.
    """
    # Allow bypass in tests / local dev
    if os.getenv("AUTH_DISABLED", "").lower() == "true":
        return AuthUser(uid="dev-user", email="dev@local", display_name="Dev User")

    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    token = header[7:]
    try:
        return verify_token(token)
    except Exception as exc:
        raise HTTPException(status_code=401, detail=f"Invalid token: {exc}") from exc
