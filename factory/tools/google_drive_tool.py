"""Google Drive tool — manage project folders and file organization."""

import logging
import os

from google.oauth2 import service_account
from googleapiclient.discovery import build

log = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/drive.file"]

# Root folder in Drive where all AI Factory projects live
ROOT_FOLDER_ID = os.getenv("GDRIVE_ROOT_FOLDER_ID", "")


def _get_creds():
    cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if cred_path:
        return service_account.Credentials.from_service_account_file(cred_path, scopes=SCOPES)
    import google.auth
    creds, _ = google.auth.default(scopes=SCOPES)
    return creds


def _drive_service():
    return build("drive", "v3", credentials=_get_creds(), cache_discovery=False)


def ensure_project_folder(project_id: str, uid: str) -> str:
    """Create (or find) the Drive folder for a user's project.

    Structure: AI Factory / {uid} / {project_id}
    Returns the folder ID.
    """
    drive = _drive_service()

    # Find or create the user folder
    user_folder = _find_or_create_folder(drive, uid, ROOT_FOLDER_ID or None)
    # Find or create the project folder
    project_folder = _find_or_create_folder(drive, project_id, user_folder)

    log.info("Drive project folder: %s/%s → %s", uid, project_id, project_folder)
    return project_folder


def _find_or_create_folder(drive, name: str, parent_id: str | None) -> str:
    """Find an existing folder by name under parent, or create one."""
    query = f"name='{name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    if parent_id:
        query += f" and '{parent_id}' in parents"
    results = drive.files().list(q=query, fields="files(id)", pageSize=1).execute()
    files = results.get("files", [])
    if files:
        return files[0]["id"]

    meta = {"name": name, "mimeType": "application/vnd.google-apps.folder"}
    if parent_id:
        meta["parents"] = [parent_id]
    folder = drive.files().create(body=meta, fields="id").execute()
    return folder["id"]


def share_with_user(file_id: str, email: str, role: str = "writer") -> None:
    """Share a Drive file/folder with a user by email."""
    drive = _drive_service()
    drive.permissions().create(
        fileId=file_id,
        body={"type": "user", "role": role, "emailAddress": email},
        sendNotificationEmail=False,
    ).execute()
    log.info("Shared %s with %s (%s)", file_id, email, role)
