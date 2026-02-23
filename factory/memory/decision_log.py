"""Decision log — records structured decisions made by each team agent.

Each pipeline run logs decisions (ADRs, acceptance criteria, threat models, etc.)
to Firestore under users/{uid}/projects/{id}/decisions/{decision_id}.
These are surfaced in the frontend Memory Map when a user clicks on an agent node.

Decision types:
  ADR                 Architecture Decision Record      (solution_arch)
  acceptance_criteria Business acceptance criteria      (biz_analysis)
  threat_model        Security threat model             (security_eng)
  api_contract        API design contract               (api_design)
  compliance          Compliance requirement            (compliance)
  architecture        General architectural decision    (frontend/backend/db/data)
  test_plan           QA test plan decision             (qa_eng)
  deployment          Deployment / ops strategy         (devops, sre_ops)
  feature             Feature / backlog decision        (product_mgmt, feature_eng)
  tool_choice         Tool or technology selection      (ml_eng)
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from factory.persistence.firestore_store import FirestoreStore

log = logging.getLogger(__name__)

DECISION_TYPES = [
    "ADR",
    "acceptance_criteria",
    "threat_model",
    "api_contract",
    "architecture",
    "compliance",
    "test_plan",
    "deployment",
    "feature",
    "tool_choice",
]

# Map team → default decision type
TEAM_DECISION_TYPE: dict[str, str] = {
    "product_mgmt":  "feature",
    "biz_analysis":  "acceptance_criteria",
    "solution_arch": "ADR",
    "api_design":    "api_contract",
    "ux_ui":         "architecture",
    "frontend_eng":  "architecture",
    "backend_eng":   "architecture",
    "database_eng":  "architecture",
    "data_eng":      "architecture",
    "ml_eng":        "tool_choice",
    "security_eng":  "threat_model",
    "compliance":    "compliance",
    "devops":        "deployment",
    "qa_eng":        "test_plan",
    "sre_ops":       "deployment",
    "docs_team":     "architecture",
    "feature_eng":   "feature",
}


@dataclass
class DecisionEntry:
    """A single recorded decision from an AI team agent."""
    id: str
    ts: str
    project_id: str
    team: str
    decision_type: str       # One of DECISION_TYPES
    title: str               # Short title e.g. "Use FastAPI over Django"
    rationale: str           # Why this decision was made (from LLM artifact)
    artifact_ref: str = ""   # GCS path, git SHA, or "memory://team-{team}"


class DecisionLog:
    """Records and retrieves team decisions via FirestoreStore.

    Usage in orchestrator::

        from factory.memory.decision_log import DecisionLog
        decision_log = DecisionLog(store=_get_firestore())

        # After each team runs:
        decision_log.record(uid, project_id, team=team,
                            decision_type=stage.decision_type,
                            title=stage.decision_title,
                            rationale=stage.decision_rationale)

        # In GET /decisions endpoint:
        entries = decision_log.list(uid, project_id, team="solution_arch")
    """

    def __init__(self, store: "FirestoreStore | None" = None) -> None:
        self._store = store

    # ── write ─────────────────────────────────────────────────────────────
    def record(
        self,
        uid: str,
        project_id: str,
        team: str,
        decision_type: str,
        title: str,
        rationale: str,
        artifact_ref: str = "",
    ) -> DecisionEntry:
        """Record a decision and persist it to Firestore.

        Returns the entry regardless of whether Firestore is available.
        """
        entry = DecisionEntry(
            id=str(uuid.uuid4()),
            ts=datetime.now(UTC).isoformat(),
            project_id=project_id,
            team=team,
            decision_type=decision_type or TEAM_DECISION_TYPE.get(team, "architecture"),
            title=title or f"{team} decision",
            rationale=rationale[:1000] if rationale else "",
            artifact_ref=artifact_ref,
        )
        if self._store is not None:
            try:
                self._store.save_decision(uid, project_id, entry)
            except Exception as exc:
                log.warning(
                    "DecisionLog persistence failed for %s/%s: %s",
                    team, decision_type, exc,
                )
        return entry

    # ── read ──────────────────────────────────────────────────────────────
    def list(
        self,
        uid: str,
        project_id: str,
        team: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """List decision entries for a project, optionally filtered by team.

        Returns newest-first.  Returns [] if store is unavailable.
        """
        if self._store is None:
            return []
        try:
            return self._store.list_decisions(
                uid, project_id, team=team, limit=limit
            )
        except Exception as exc:
            log.warning("DecisionLog.list failed: %s", exc)
            return []
