"""Google Sheets tool — create spreadsheets with structured data.

Uses Application Default Credentials.
"""

import logging
import os

from google.oauth2 import service_account
from googleapiclient.discovery import build

log = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]


def _get_creds():
    cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if cred_path:
        return service_account.Credentials.from_service_account_file(cred_path, scopes=SCOPES)
    import google.auth
    creds, _ = google.auth.default(scopes=SCOPES)
    return creds


def _sheets_service():
    return build("sheets", "v4", credentials=_get_creds(), cache_discovery=False)


def _drive_service():
    return build("drive", "v3", credentials=_get_creds(), cache_discovery=False)


def create_spreadsheet(
    title: str,
    headers: list[str],
    rows: list[list[str]],
    folder_id: str | None = None,
) -> dict:
    """Create a Google Sheet with headers + data rows.

    Returns: {"sheet_id": str, "sheet_url": str, "title": str, "rows": int}
    """
    drive = _drive_service()
    file_metadata = {
        "name": title,
        "mimeType": "application/vnd.google-apps.spreadsheet",
    }
    if folder_id:
        file_metadata["parents"] = [folder_id]

    sheet_file = drive.files().create(body=file_metadata, fields="id,webViewLink").execute()
    sheet_id = sheet_file["id"]
    sheet_url = sheet_file.get("webViewLink", f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit")

    # Write data
    sheets = _sheets_service()
    values = [headers] + rows
    sheets.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range="Sheet1!A1",
        valueInputOption="RAW",
        body={"values": values},
    ).execute()

    # Auto-resize + bold headers
    try:
        sheets.spreadsheets().batchUpdate(
            spreadsheetId=sheet_id,
            body={
                "requests": [
                    {
                        "repeatCell": {
                            "range": {"sheetId": 0, "startRowIndex": 0, "endRowIndex": 1},
                            "cell": {"userEnteredFormat": {"textFormat": {"bold": True}}},
                            "fields": "userEnteredFormat.textFormat.bold",
                        }
                    },
                    {
                        "autoResizeDimensions": {
                            "dimensions": {"sheetId": 0, "dimension": "COLUMNS", "startIndex": 0, "endIndex": len(headers)}
                        }
                    },
                ]
            },
        ).execute()
    except Exception:
        pass  # Non-critical formatting

    log.info("Created Google Sheet: %s (%d rows) → %s", title, len(rows), sheet_url)
    return {"sheet_id": sheet_id, "sheet_url": sheet_url, "title": title, "rows": len(rows)}
