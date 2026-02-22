"""Google Cloud Storage for large pipeline artifacts."""

import json
import os
from datetime import UTC, datetime

from google.cloud import storage  # type: ignore


class GCSArtifactStore:
    """Stores pipeline artifacts in GCS, scoped to user/project."""

    def __init__(self) -> None:
        self.bucket_name = os.getenv(
            "GCS_ARTIFACTS_BUCKET", "unicon-494419.firebasestorage.app"
        )
        self.client = storage.Client()
        self.bucket = self.client.bucket(self.bucket_name)

    def _prefix(self, uid: str, project_id: str) -> str:
        return f"users/{uid}/projects/{project_id}/artifacts"

    def save_artifacts(
        self,
        uid: str,
        project_id: str,
        task_id: str,
        requirement: str,
        artifacts: dict[str, str],
    ) -> str:
        """Save all pipeline artifacts as JSON in GCS. Returns the GCS path."""
        prefix = self._prefix(uid, project_id)
        path = f"{prefix}/{task_id}/artifacts.json"
        blob = self.bucket.blob(path)
        payload = {
            "task_id": task_id,
            "project_id": project_id,
            "requirement": requirement,
            "saved_at": datetime.now(UTC).isoformat(),
            "teams": list(artifacts.keys()),
            "artifacts": artifacts,
        }
        blob.upload_from_string(
            json.dumps(payload, indent=2), content_type="application/json"
        )

        # Also save per-team files for easy browsing
        for team, artifact in artifacts.items():
            team_path = f"{prefix}/{task_id}/{team}.txt"
            team_blob = self.bucket.blob(team_path)
            team_blob.upload_from_string(artifact, content_type="text/plain")

        return f"gs://{self.bucket_name}/{path}"

    def load_artifacts(self, uid: str, project_id: str, task_id: str) -> dict | None:
        """Load pipeline artifacts from GCS."""
        prefix = self._prefix(uid, project_id)
        path = f"{prefix}/{task_id}/artifacts.json"
        blob = self.bucket.blob(path)
        if not blob.exists():
            return None
        return json.loads(blob.download_as_string())
