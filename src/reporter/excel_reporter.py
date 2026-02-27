# Job tracker using Google Sheets API
# Each run writes to its own date-stamped tab (e.g., "2026-02-26").
# All tabs are read for deduplication and application history.
#
# Auth split:
#   - Sheets (read/write tracker): service account (inputs/google_credentials.json)
#   - Drive + Docs (create Google Docs): OAuth 2.0 as user (inputs/oauth_credentials.json)
#     First run opens browser for one-time auth; token cached in inputs/oauth_token.json.

import io
from datetime import datetime
from pathlib import Path

# Service account — used for Sheets only
CREDENTIALS_FILE = Path("inputs/google_credentials.json")
SHEETS_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# OAuth 2.0 — used for Drive + Docs (runs as the user, has real storage quota)
OAUTH_CREDENTIALS_FILE = Path("inputs/oauth_credentials.json")
OAUTH_TOKEN_FILE = Path("inputs/oauth_token.json")
DRIVE_SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/documents",
]

COLUMNS = [
    "Company",
    "Job Title",
    "Brief Description",
    "Application URL",
    "Resume Path",
    "Cover Letter Path",
    "Match Score",
    "Date Found",
    "Applied",
    "Status",
]

URL_COL_INDEX = 3   # 0-based: Application URL is the 4th column (D)
APPLIED_COL_INDEX = 8  # 0-based: Applied is the 9th column (I)


def _sheets_service():
    """Sheets operations use the service account."""
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    creds = service_account.Credentials.from_service_account_file(
        str(CREDENTIALS_FILE), scopes=SHEETS_SCOPES
    )
    return build("sheets", "v4", credentials=creds)


def _user_creds():
    """
    OAuth 2.0 credentials for Drive/Docs — runs as the user's Google account.
    Opens a browser on the first call; subsequent calls use the cached token.
    Requires inputs/oauth_credentials.json (OAuth Desktop App from Google Cloud Console).
    """
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds = None
    if OAUTH_TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(OAUTH_TOKEN_FILE), DRIVE_SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(OAUTH_CREDENTIALS_FILE), DRIVE_SCOPES
            )
            creds = flow.run_local_server(port=0)
        OAUTH_TOKEN_FILE.write_text(creds.to_json())

    return creds


def _drive_service():
    """Drive operations run as the user (OAuth 2.0)."""
    from googleapiclient.discovery import build
    return build("drive", "v3", credentials=_user_creds())


def _docs_service():
    """Docs operations run as the user (OAuth 2.0)."""
    from googleapiclient.discovery import build
    return build("docs", "v1", credentials=_user_creds())


def _list_tabs(service, sheet_id: str) -> list[dict]:
    """Return list of {title, sheetId} for all tabs in the spreadsheet."""
    result = service.spreadsheets().get(
        spreadsheetId=sheet_id,
        fields="sheets.properties",
    ).execute()
    return [
        {"title": s["properties"]["title"], "sheetId": s["properties"]["sheetId"]}
        for s in result.get("sheets", [])
    ]


def _get_or_create_tab(service, sheet_id: str, tab_name: str) -> int:
    """
    Return the sheetId (int) for tab_name, creating it with headers if needed.
    """
    tabs = _list_tabs(service, sheet_id)
    for tab in tabs:
        if tab["title"] == tab_name:
            return tab["sheetId"]

    # Create the tab
    service.spreadsheets().batchUpdate(
        spreadsheetId=sheet_id,
        body={"requests": [{"addSheet": {"properties": {"title": tab_name}}}]},
    ).execute()

    # Write header row
    service.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range=f"'{tab_name}'!A1",
        valueInputOption="RAW",
        body={"values": [COLUMNS]},
    ).execute()

    # Bold the header row — re-fetch sheetId after creation
    tabs = _list_tabs(service, sheet_id)
    new_sheet_id = next(t["sheetId"] for t in tabs if t["title"] == tab_name)
    service.spreadsheets().batchUpdate(
        spreadsheetId=sheet_id,
        body={"requests": [{
            "repeatCell": {
                "range": {"sheetId": new_sheet_id, "startRowIndex": 0, "endRowIndex": 1},
                "cell": {"userEnteredFormat": {"textFormat": {"bold": True}}},
                "fields": "userEnteredFormat.textFormat.bold",
            }
        }]},
    ).execute()

    return new_sheet_id


def init_workbook(sheet_id: str) -> None:
    """Verify sheet connectivity. Tabs are created per-run, not pre-created."""
    if not sheet_id:
        return
    service = _sheets_service()
    service.spreadsheets().get(
        spreadsheetId=sheet_id,
        fields="spreadsheetId",
    ).execute()


def get_tracked_urls(sheet_id: str) -> set[str]:
    """Return the set of job URLs already recorded across ALL tabs."""
    if not sheet_id:
        return set()
    try:
        service = _sheets_service()
        tabs = _list_tabs(service, sheet_id)
        if not tabs:
            return set()

        # Batch-read URL column (D) from every tab in one API call
        ranges = [f"'{t['title']}'!D:D" for t in tabs]
        result = service.spreadsheets().values().batchGet(
            spreadsheetId=sheet_id,
            ranges=ranges,
        ).execute()

        urls: set[str] = set()
        for value_range in result.get("valueRanges", []):
            for row in value_range.get("values", [])[1:]:  # skip header
                if row and row[0].strip():
                    urls.add(row[0].strip())
        return urls
    except Exception:
        return set()


def get_application_history(sheet_id: str) -> tuple[list[dict], list[dict]]:
    """
    Read all tabs and return jobs the user has acted on.

    Returns:
        (applied_jobs, skipped_jobs) — each is a list of
        {"company": str, "title": str, "summary": str}
    """
    if not sheet_id:
        return [], []
    try:
        service = _sheets_service()
        tabs = _list_tabs(service, sheet_id)
        if not tabs:
            return [], []

        # Batch-read columns A,B,C,I (Company, Title, Brief Description, Applied)
        # We read A:I to get all relevant columns cheaply
        ranges = [f"'{t['title']}'!A:I" for t in tabs]
        result = service.spreadsheets().values().batchGet(
            spreadsheetId=sheet_id,
            ranges=ranges,
        ).execute()

        applied: list[dict] = []
        skipped: list[dict] = []
        applied_values = {"applied", "yes", "y"}
        skipped_values = {"did not apply", "no", "n", "skip", "skipped"}

        for value_range in result.get("valueRanges", []):
            rows = value_range.get("values", [])
            for row in rows[1:]:  # skip header
                if len(row) <= APPLIED_COL_INDEX:
                    continue
                applied_val = row[APPLIED_COL_INDEX].strip().lower()
                if not applied_val:
                    continue

                entry = {
                    "company": row[0] if len(row) > 0 else "",
                    "title": row[1] if len(row) > 1 else "",
                    "summary": row[2] if len(row) > 2 else "",
                }

                if applied_val in applied_values:
                    applied.append(entry)
                elif applied_val in skipped_values:
                    skipped.append(entry)

        return applied, skipped
    except Exception:
        return [], []


def append_job(sheet_id: str, job: dict) -> None:
    """Append a processed job as a new row in today's tab."""
    if not sheet_id:
        return

    score = job.get("match_score") or 0
    row = [
        job.get("company", ""),
        job.get("title", ""),
        job.get("match_summary", ""),
        job.get("url", ""),
        job.get("resume_path", ""),
        job.get("cover_letter_path", ""),
        score,
        job.get("date_found", datetime.now().strftime("%Y-%m-%d")),
        "",              # Applied — user fills in
        "To Apply",
    ]

    today_tab = datetime.now().strftime("%Y-%m-%d")
    service = _sheets_service()
    tab_sheet_id = _get_or_create_tab(service, sheet_id, today_tab)

    result = service.spreadsheets().values().append(
        spreadsheetId=sheet_id,
        range=f"'{today_tab}'!A:J",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={"values": [row]},
    ).execute()

    # Color-code row by match score
    if isinstance(score, int) and score > 0:
        updated_range = result.get("updates", {}).get("updatedRange", "")
        try:
            # Parse row number from range like "'2026-02-26'!A52:J52"
            row_idx = int(updated_range.split("!A")[1].split(":")[0]) - 1  # 0-based
            if score >= 85:
                bg = {"red": 0.78, "green": 0.94, "blue": 0.81}  # green
            elif score >= 70:
                bg = {"red": 1.0, "green": 0.92, "blue": 0.61}   # yellow
            else:
                bg = None

            if bg:
                service.spreadsheets().batchUpdate(
                    spreadsheetId=sheet_id,
                    body={"requests": [{
                        "repeatCell": {
                            "range": {
                                "sheetId": tab_sheet_id,
                                "startRowIndex": row_idx,
                                "endRowIndex": row_idx + 1,
                            },
                            "cell": {"userEnteredFormat": {"backgroundColor": bg}},
                            "fields": "userEnteredFormat.backgroundColor",
                        }
                    }]},
                ).execute()
        except Exception:
            pass  # color is non-critical


def create_gdoc_from_docx(docx_path: str, title: str, folder_id: str) -> str:
    """
    Upload a local .docx file to Google Drive, converting it to a native Google Doc.

    Drive converts the DOCX during upload, preserving tables, fonts, spacing, and
    all formatting that manual text-extraction would lose.
    Converted Google Docs don't count against storage quota.

    Returns the Google Doc URL on success, raises on failure.
    """
    from googleapiclient.http import MediaFileUpload

    drive_svc = _drive_service()

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

    return f"https://docs.google.com/document/d/{file_obj['id']}/edit"
