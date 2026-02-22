"""Google Docs tool — create and write documents in Google Drive.

Uses Application Default Credentials (same SA as Cloud Run).
Documents are created in a shared Drive folder per project.
"""

import logging
import os

from google.oauth2 import service_account
from googleapiclient.discovery import build

log = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive.file",
]


def _get_creds():
    """Build credentials from ADC or explicit path."""
    cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if cred_path:
        return service_account.Credentials.from_service_account_file(cred_path, scopes=SCOPES)
    # On Cloud Run, use default credentials
    import google.auth
    creds, _ = google.auth.default(scopes=SCOPES)
    return creds


def _docs_service():
    return build("docs", "v1", credentials=_get_creds(), cache_discovery=False)


def _drive_service():
    return build("drive", "v3", credentials=_get_creds(), cache_discovery=False)


def create_document(title: str, content: str, folder_id: str | None = None) -> dict:
    """Create a Google Doc with the given title and body text.

    Returns: {"doc_id": str, "doc_url": str, "title": str}
    """
    drive = _drive_service()
    file_metadata = {
        "name": title,
        "mimeType": "application/vnd.google-apps.document",
    }
    if folder_id:
        file_metadata["parents"] = [folder_id]

    doc_file = drive.files().create(body=file_metadata, fields="id,webViewLink").execute()
    doc_id = doc_file["id"]
    doc_url = doc_file.get("webViewLink", f"https://docs.google.com/document/d/{doc_id}/edit")

    # Insert content
    if content.strip():
        docs = _docs_service()
        requests = [{"insertText": {"location": {"index": 1}, "text": content}}]
        docs.documents().batchUpdate(documentId=doc_id, body={"requests": requests}).execute()

    log.info("Created Google Doc: %s → %s", title, doc_url)
    return {"doc_id": doc_id, "doc_url": doc_url, "title": title}


def append_to_document(doc_id: str, content: str) -> dict:
    """Append text to an existing Google Doc."""
    docs = _docs_service()
    doc = docs.documents().get(documentId=doc_id).execute()
    end_index = doc["body"]["content"][-1]["endIndex"] - 1
    requests = [{"insertText": {"location": {"index": max(end_index, 1)}, "text": "\n" + content}}]
    docs.documents().batchUpdate(documentId=doc_id, body={"requests": requests}).execute()
    return {"doc_id": doc_id, "appended": True}
