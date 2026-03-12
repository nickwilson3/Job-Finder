"""Per-user Google Drive upload helper for the web app.

Each user who connects Google Drive gets their own "Job Finder Applications"
folder created automatically on first upload.  Subsequent uploads go into
that same folder.  The folder ID is cached on the User DB record.

Auth: OAuth 2.0 token stored per-user at user_data/{id}/inputs/google_token.json
"""
import json
from pathlib import Path

DRIVE_SCOPES = [
    "https://www.googleapis.com/auth/drive",
]
OAUTH_CREDENTIALS_FILE = Path("inputs/oauth_credentials.json")
FOLDER_NAME = "Job Finder Applications"


def _get_user_creds(token_path: Path):
    """Load and auto-refresh a user's Google OAuth token."""
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request

    creds = Credentials.from_authorized_user_file(str(token_path), DRIVE_SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_path.write_text(creds.to_json())
    return creds


def _get_or_create_folder(drive_svc, folder_id_cached: str | None) -> str:
    """
    Return the 'Job Finder Applications' folder ID.
    If folder_id_cached is given and still exists, reuse it.
    Otherwise search for it or create it.
    """
    # Verify cached ID still exists
    if folder_id_cached:
        try:
            drive_svc.files().get(fileId=folder_id_cached, fields="id").execute()
            return folder_id_cached
        except Exception:
            pass  # folder was deleted, fall through to create

    # Search for existing folder by name
    query = (
        f"name='{FOLDER_NAME}' and mimeType='application/vnd.google-apps.folder'"
        " and trashed=false"
    )
    results = drive_svc.files().list(q=query, fields="files(id)").execute()
    files = results.get("files", [])
    if files:
        return files[0]["id"]

    # Create it
    meta = {
        "name": FOLDER_NAME,
        "mimeType": "application/vnd.google-apps.folder",
    }
    folder = drive_svc.files().create(body=meta, fields="id").execute()
    return folder["id"]


def upload_to_user_drive(
    user_id: int,
    docx_path: str,
    title: str,
    cached_folder_id: str | None = None,
) -> tuple[str, str]:
    """
    Upload a DOCX to the user's Google Drive as a native Google Doc.

    Returns (google_doc_url, folder_id).
    folder_id should be saved back to user.google_drive_folder_id for reuse.

    Raises if the user has no token file or if the upload fails.
    """
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    from web.storage import google_token_path

    token_path = google_token_path(user_id)
    if not token_path.exists():
        raise RuntimeError("Google Drive not connected for this user.")

    creds = _get_user_creds(token_path)
    drive_svc = build("drive", "v3", credentials=creds)

    folder_id = _get_or_create_folder(drive_svc, cached_folder_id)

    file_metadata = {
        "name": title,
        "mimeType": "application/vnd.google-apps.document",
        "parents": [folder_id],
    }
    media = MediaFileUpload(
        docx_path,
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    file_obj = drive_svc.files().create(
        body=file_metadata,
        media_body=media,
        fields="id",
    ).execute()

    url = f"https://docs.google.com/document/d/{file_obj['id']}/edit"
    return url, folder_id
