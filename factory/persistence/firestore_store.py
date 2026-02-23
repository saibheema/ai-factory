"""Firestore persistence layer — user-scoped project data.

Firestore schema
================
users/{uid}
  ├── email, display_name, created_at, last_login
  ├── config/git_token             — PAT stored once per user (not per project)
  └── projects/{project_id}
        ├── name, created_at, updated_at
        ├── config/team_settings   — per-team model / budget / API-key
        ├── config/git             — git_url, git_token_set (token lives at user level)
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

    # ── User-level Git Token (PAT stored once, applies to all projects) ──
    def save_user_git_token(self, uid: str, token: str) -> None:
        """Store the GitHub PAT at the user level — one token for all projects."""
        ref = self._user_ref(uid).collection("config").document("git_token")
        ref.set({"token": token, "updated_at": self._now()})

    def get_user_git_token(self, uid: str) -> str:
        """Retrieve user-level GitHub PAT."""
        ref = self._user_ref(uid).collection("config").document("git_token")
        doc = ref.get()
        return doc.to_dict().get("token", "") if doc.exists else ""

    def delete_user_git_token(self, uid: str) -> None:
        self._user_ref(uid).collection("config").document("git_token").delete()

    def user_git_token_set(self, uid: str) -> bool:
        ref = self._user_ref(uid).collection("config").document("git_token")
        doc = ref.get()
        return doc.exists and bool(doc.to_dict().get("token"))

    # ── Git Config (URL per-project, token at user level) ───
    def get_git_config(self, uid: str, project_id: str) -> dict | None:
        ref = self._project_ref(uid, project_id).collection("config").document("git")
        doc = ref.get()
        if not doc.exists:
            return None
        data = doc.to_dict()
        # Reflect whether the user-level token is set
        data["git_token_set"] = self.user_git_token_set(uid)
        return data

    def save_git_config(self, uid: str, project_id: str, git_url: str, git_token: str = "") -> None:
        """Save URL per-project. If a token is supplied here, promote it to user level."""
        ref = self._project_ref(uid, project_id).collection("config").document("git")
        ref.set({
            "git_url": git_url,
            "updated_at": self._now(),
        })
        if git_token:
            # Promote to user-level — applies to all projects
            self.save_user_git_token(uid, git_token)

    def get_git_token(self, uid: str, project_id: str = "") -> str:  # project_id kept for compat
        """Always return the user-level token."""
        return self.get_user_git_token(uid)

    # ── Decision Log ─────────────────────────────────────────────────────
    def save_decision(self, uid: str, project_id: str, entry: object) -> None:
        """Persist a DecisionEntry under users/{uid}/projects/{id}/decisions/{id}."""
        ref = (
            self._project_ref(uid, project_id)
            .collection("decisions")
            .document(entry.id)
        )
        ref.set(
            {
                "id": entry.id,
                "ts": entry.ts,
                "project_id": entry.project_id,
                "team": entry.team,
                "decision_type": entry.decision_type,
                "title": entry.title,
                "rationale": entry.rationale,
                "artifact_ref": entry.artifact_ref,
            }
        )

    def list_decisions(
        self,
        uid: str,
        project_id: str,
        team: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """Return decision entries (newest-first), optionally filtered by team.

        Filtering is done in Python to avoid Firestore composite-index requirements.
        """
        ref = self._project_ref(uid, project_id).collection("decisions")
        docs = ref.limit(max(limit * 3, 200)).stream()
        results: list[dict] = []
        for d in docs:
            if d.exists:
                data = d.to_dict()
                if team is None or data.get("team") == team:
                    results.append(data)
                    if len(results) >= limit:
                        break
        # Sort newest-first by timestamp string (ISO 8601 sorts lexicographically)
        results.sort(key=lambda x: x.get("ts", ""), reverse=True)
        return results
