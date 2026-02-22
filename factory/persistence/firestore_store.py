"""Firestore persistence layer — user-scoped project data.

Firestore schema
================
users/{uid}
  ├── email, display_name, created_at, last_login
  └── projects/{project_id}
        ├── name, created_at, updated_at, git_url
        ├── config/team_settings   — per-team model / budget / API-key
        ├── config/git             — git_url, git_token_set
        ├── config/git_token       — encrypted token (separate doc)
        ├── memory/{bank_id}       — items[]
        └── runs/{task_id}         — full pipeline run payload
"""

import os
from datetime import UTC, datetime
from typing import Any

from google.cloud import firestore  # type: ignore


class FirestoreStore:
    """Stores user projects, memory, settings, and pipeline runs in Firestore."""

    def __init__(self) -> None:
        project_id = os.getenv("GCP_PROJECT_ID", "unicon-494419")
        self.db = firestore.Client(project=project_id)

    # ── helpers ──────────────────────────────────────────────
    def _now(self) -> str:
        return datetime.now(UTC).isoformat()

    def _user_ref(self, uid: str):
        return self.db.collection("users").document(uid)

    def _project_ref(self, uid: str, project_id: str):
        return self._user_ref(uid).collection("projects").document(project_id)

    # ── User Profile ────────────────────────────────────────
    def ensure_user(self, uid: str, email: str = "", display_name: str = "") -> dict:
        ref = self._user_ref(uid)
        doc = ref.get()
        if doc.exists:
            ref.update({"last_login": self._now()})
            return doc.to_dict()
        profile = {
            "uid": uid,
            "email": email,
            "display_name": display_name,
            "created_at": self._now(),
            "last_login": self._now(),
        }
        ref.set(profile)
        return profile

    # ── Projects ────────────────────────────────────────────
    def list_projects(self, uid: str) -> list[dict]:
        docs = self._user_ref(uid).collection("projects").stream()
        return [{"id": d.id, **d.to_dict()} for d in docs]

    def get_project(self, uid: str, project_id: str) -> dict | None:
        doc = self._project_ref(uid, project_id).get()
        return {"id": doc.id, **doc.to_dict()} if doc.exists else None

    def upsert_project(self, uid: str, project_id: str, data: dict | None = None) -> dict:
        ref = self._project_ref(uid, project_id)
        doc = ref.get()
        payload: dict[str, Any] = data or {}
        if doc.exists:
            payload["updated_at"] = self._now()
            ref.update(payload)
        else:
            payload.setdefault("name", project_id)
            payload.setdefault("created_at", self._now())
            payload["updated_at"] = self._now()
            payload["project_id"] = project_id
            ref.set(payload)
        return {"id": project_id, **ref.get().to_dict()}

    def delete_project(self, uid: str, project_id: str) -> None:
        self._project_ref(uid, project_id).delete()

    # ── Memory Banks (scoped to user + project) ────────────
    def recall(self, uid: str, project_id: str, bank_id: str, limit: int = 5) -> list[str]:
        ref = self._project_ref(uid, project_id).collection("memory").document(bank_id)
        doc = ref.get()
        if not doc.exists:
            return []
        items = doc.to_dict().get("items", [])
        return items[-limit:]

    def retain(self, uid: str, project_id: str, bank_id: str, item: str) -> None:
        ref = self._project_ref(uid, project_id).collection("memory").document(bank_id)
        doc = ref.get()
        if doc.exists:
            ref.update({
                "items": firestore.ArrayUnion([item]),
                "updated_at": self._now(),
            })
        else:
            ref.set({
                "items": [item],
                "created_at": self._now(),
                "updated_at": self._now(),
            })

    def memory_snapshot(self, uid: str, project_id: str) -> dict[str, list[str]]:
        docs = self._project_ref(uid, project_id).collection("memory").stream()
        return {d.id: d.to_dict().get("items", []) for d in docs}

    # ── Team Settings (model, budget, API key per user+project) ──
    def get_team_settings(self, uid: str, project_id: str) -> dict:
        ref = self._project_ref(uid, project_id).collection("config").document("team_settings")
        doc = ref.get()
        return doc.to_dict() if doc.exists else {}

    def save_team_settings(self, uid: str, project_id: str, settings: dict) -> None:
        ref = self._project_ref(uid, project_id).collection("config").document("team_settings")
        ref.set(settings, merge=True)

    # ── Pipeline Runs ───────────────────────────────────────
    def save_run(self, uid: str, project_id: str, task_id: str, data: dict) -> None:
        ref = self._project_ref(uid, project_id).collection("runs").document(task_id)
        data["updated_at"] = self._now()
        ref.set(data, merge=True)

    def get_run(self, uid: str, project_id: str, task_id: str) -> dict | None:
        ref = self._project_ref(uid, project_id).collection("runs").document(task_id)
        doc = ref.get()
        return doc.to_dict() if doc.exists else None

    def list_runs(self, uid: str, project_id: str, limit: int = 20) -> list[dict]:
        query = (
            self._project_ref(uid, project_id)
            .collection("runs")
            .order_by("updated_at", direction=firestore.Query.DESCENDING)
            .limit(limit)
        )
        return [{"id": d.id, **d.to_dict()} for d in query.stream()]

    # ── Git Config ──────────────────────────────────────────
    def get_git_config(self, uid: str, project_id: str) -> dict | None:
        ref = self._project_ref(uid, project_id).collection("config").document("git")
        doc = ref.get()
        return doc.to_dict() if doc.exists else None

    def save_git_config(self, uid: str, project_id: str, git_url: str, git_token: str = "") -> None:
        ref = self._project_ref(uid, project_id).collection("config").document("git")
        ref.set({
            "git_url": git_url,
            "git_token_set": bool(git_token),
            "updated_at": self._now(),
        })
        if git_token:
            token_ref = self._project_ref(uid, project_id).collection("config").document("git_token")
            token_ref.set({"token": git_token, "updated_at": self._now()})

    def get_git_token(self, uid: str, project_id: str) -> str:
        ref = self._project_ref(uid, project_id).collection("config").document("git_token")
        doc = ref.get()
        return doc.to_dict().get("token", "") if doc.exists else ""
