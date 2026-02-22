"""GCS artifact tool — upload files to Google Cloud Storage.

For teams that produce code/configs when no Git repo is configured.
"""

import json
import logging
import os

from google.cloud import storage

log = logging.getLogger(__name__)

BUCKET_NAME = os.getenv("GCS_BUCKET", "unicon-494419.firebasestorage.app")


def _client():
    return storage.Client(project=os.getenv("GCP_PROJECT_ID", "unicon-494419"))


def upload_artifact(
    uid: str,
    project_id: str,
    team: str,
    filename: str,
    content: str,
    content_type: str = "text/plain",
) -> dict:
    """Upload a single artifact file to GCS.

    Path: users/{uid}/projects/{project_id}/artifacts/{team}/{filename}
    Returns: {"gcs_path": str, "public_url": str}
    """
    client = _client()
    bucket = client.bucket(BUCKET_NAME)
    blob_path = f"users/{uid}/projects/{project_id}/artifacts/{team}/{filename}"
    blob = bucket.blob(blob_path)
    blob.upload_from_string(content, content_type=content_type)

    log.info("GCS upload: gs://%s/%s", BUCKET_NAME, blob_path)
    return {
        "gcs_path": f"gs://{BUCKET_NAME}/{blob_path}",
        "public_url": f"https://storage.googleapis.com/{BUCKET_NAME}/{blob_path}",
    }


def upload_json(uid: str, project_id: str, team: str, filename: str, data: dict) -> dict:
    """Upload JSON data to GCS."""
    return upload_artifact(uid, project_id, team, filename, json.dumps(data, indent=2), "application/json")
