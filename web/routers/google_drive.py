"""Google Drive OAuth 2.0 flow for per-user Drive integration.

Flow:
  1. GET /auth/google         — redirects user to Google consent screen
  2. GET /auth/google/callback — Google redirects here with auth code
                                 → exchanges for tokens → saves token file
                                 → marks user.google_drive_connected = True
  3. POST /auth/google/disconnect — removes token file, clears flag

The OAuth app credentials are read from inputs/oauth_credentials.json
(the same file used by Nick's CLI).  The redirect URI
http://localhost:8000/auth/google/callback must be added to the
authorized redirect URIs for that credential in Google Cloud Console.
"""
import hashlib
import hmac
import json
import os
import secrets
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from web.auth import get_current_user
from web.database import get_db
from web.models import User
from web.storage import google_token_path, inputs_dir

router = APIRouter()

OAUTH_CREDENTIALS_FILE = Path("inputs/oauth_credentials.json")
DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive"]
REDIRECT_URI = os.environ.get("GOOGLE_REDIRECT_URI", "https://job-finder-fdjb.onrender.com/auth/google/callback")


def _client_config() -> dict:
    """Read OAuth client_id and client_secret.

    Checks (in order):
      1. GOOGLE_OAUTH_CREDENTIALS env var — full JSON string (used in production/Render)
      2. inputs/oauth_credentials.json file — used locally
    """
    raw_json = os.environ.get("GOOGLE_OAUTH_CREDENTIALS")
    if raw_json:
        raw = json.loads(raw_json)
    elif OAUTH_CREDENTIALS_FILE.exists():
        raw = json.loads(OAUTH_CREDENTIALS_FILE.read_text())
    else:
        raise RuntimeError(
            "Google OAuth credentials not found. "
            "Set the GOOGLE_OAUTH_CREDENTIALS env var (paste the full JSON from Google Cloud Console), "
            "or place the file at inputs/oauth_credentials.json."
        )
    cred = raw.get("installed") or raw.get("web")
    if not cred:
        raise RuntimeError("Unrecognised OAuth credential format.")
    return {
        "web": {
            "client_id": cred["client_id"],
            "client_secret": cred["client_secret"],
            "auth_uri": cred.get("auth_uri", "https://accounts.google.com/o/oauth2/auth"),
            "token_uri": cred.get("token_uri", "https://oauth2.googleapis.com/token"),
            "redirect_uris": [REDIRECT_URI],
        }
    }


def _sign_state(user_id: int, nonce: str) -> str:
    secret = os.environ.get("WEB_SECRET_KEY", "fallback-secret")
    msg = f"{user_id}:{nonce}"
    sig = hmac.new(secret.encode(), msg.encode(), hashlib.sha256).hexdigest()
    return f"{user_id}:{nonce}:{sig}"


def _verify_state(state: str) -> int | None:
    """Returns user_id if state is valid, else None."""
    try:
        user_id_str, nonce, sig = state.split(":")
        expected = _sign_state(int(user_id_str), nonce)
        if not hmac.compare_digest(state, expected):
            return None
        return int(user_id_str)
    except Exception:
        return None


@router.get("/auth/google")
def google_auth(request: Request, db: Session = Depends(get_db)):
    """Kick off Google OAuth flow."""
    user: User = get_current_user(request, db)

    from google_auth_oauthlib.flow import Flow

    nonce = secrets.token_hex(16)
    state = _sign_state(user.id, nonce)

    flow = Flow.from_client_config(
        _client_config(),
        scopes=DRIVE_SCOPES,
        redirect_uri=REDIRECT_URI,
        autogenerate_code_verifier=False,  # we have a client_secret; no PKCE needed
    )
    authorization_url, _ = flow.authorization_url(
        access_type="offline",
        state=state,
        prompt="consent",  # always ask so we get a refresh_token
    )
    return RedirectResponse(authorization_url)


@router.get("/auth/google/callback")
def google_callback(request: Request, db: Session = Depends(get_db)):
    """Handle Google's OAuth redirect, save token, redirect to settings."""
    from google_auth_oauthlib.flow import Flow

    state = request.query_params.get("state", "")
    code = request.query_params.get("code", "")
    error = request.query_params.get("error", "")

    if error:
        return RedirectResponse("/settings?error=google_denied")

    user_id = _verify_state(state)
    if user_id is None:
        return RedirectResponse("/settings?error=google_state_invalid")

    user: User = db.get(User, user_id)
    if not user:
        return RedirectResponse("/settings?error=google_user_not_found")

    try:
        # Allow http for localhost during development — must be set BEFORE flow creation
        os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

        flow = Flow.from_client_config(
            _client_config(),
            scopes=DRIVE_SCOPES,
            redirect_uri=REDIRECT_URI,
        )
        # Build the full callback URL for token exchange
        callback_url = str(request.url)
        flow.fetch_token(authorization_response=callback_url)

        token_path = google_token_path(user_id)
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(flow.credentials.to_json())

        user.google_drive_connected = True
        db.commit()
    except Exception as e:
        import traceback
        import logging
        logging.getLogger("job_finder.google_drive").error(
            "Google token exchange failed: %s\n%s", e, traceback.format_exc()
        )
        return RedirectResponse(f"/settings?error=google_token_failed&detail={type(e).__name__}")

    return RedirectResponse("/settings?google_connected=1")


@router.post("/auth/google/disconnect")
def google_disconnect(request: Request, db: Session = Depends(get_db)):
    """Remove token and clear Drive connection."""
    user: User = get_current_user(request, db)

    token_path = google_token_path(user.id)
    if token_path.exists():
        token_path.unlink()

    user.google_drive_connected = False
    user.google_drive_folder_id = None
    db.commit()

    return JSONResponse({"status": "disconnected"})
