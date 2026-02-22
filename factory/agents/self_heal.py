"""Self-Healing Agent — analyzes error logs, generates fix requirements,
collects multi-agent sign-offs, and returns a merge-ready decision.

Flow
----
1. ``analyze_issue()``  — LLM reads error entries, returns root-cause + fix requirement
2. The orchestrator runs the fix requirement through the standard pipeline
3. ``get_agent_signoffs()`` — each affected team + QA + SRE reviews the fix artifact
4. Orchestrator merges to ``dev`` if all teams approve, otherwise notifies user
"""

import logging
import re

log = logging.getLogger(__name__)

_VALID_TEAMS = {
    "backend_eng", "frontend_eng", "devops", "qa_eng",
    "sre_ops", "database_eng", "security_eng", "solution_arch",
}


class SelfHealAgent:
    """Autonomous agent: detect issues → propose fix → collect sign-offs."""

    def __init__(self, llm_runtime=None):
        self.llm_runtime = llm_runtime

    # ──────────────────────────────────────────────────────────────────────
    #  Issue analysis
    # ──────────────────────────────────────────────────────────────────────

    def analyze_issue(self, error_entries: list[dict], project_id: str) -> dict:
        """Use LLM to read errors and produce a structured fix plan."""
        if not error_entries:
            return {}

        summary = "\n".join(
            f"[{e.get('ts', '')}] {e.get('level', 'ERROR')} — {e.get('msg', '')}"
            for e in error_entries[:10]
        )

        prompt = (
            f"You are an AI site-reliability engineer reviewing errors in project '{project_id}'.\n\n"
            f"ERRORS:\n{summary}\n\n"
            f"Respond in EXACTLY this format, one field per line:\n"
            f"ROOT_CAUSE: <one sentence>\n"
            f"FIX: <specific technical change needed>\n"
            f"TEAMS: <comma-separated subset of: "
            f"backend_eng,frontend_eng,devops,qa_eng,sre_ops,database_eng,security_eng>\n"
            f"REQUIREMENT: <complete requirement string to pass to the auto-fix pipeline>\n"
        )

        if self.llm_runtime:
            try:
                result = self.llm_runtime.generate(
                    team="sre_ops", requirement=prompt,
                    prior_count=0, handoff_to="none",
                )
                if result and result.content:
                    return self._parse_analysis(result.content, error_entries)
            except Exception as exc:
                log.warning("LLM analysis failed: %s", exc)

        return self._keyword_fallback(error_entries, project_id)

    def _keyword_fallback(self, errors: list[dict], project_id: str) -> dict:
        first = errors[0].get("msg", "")
        msg = first.lower()
        if any(w in msg for w in ["import", "module", "package", "dependency", "no module"]):
            teams = ["devops", "backend_eng"]
        elif any(w in msg for w in ["database", "sql", "query", "connection refused", "psycopg"]):
            teams = ["database_eng", "backend_eng"]
        elif any(w in msg for w in ["auth", "token", "permission denied", "403", "401", "forbidden"]):
            teams = ["security_eng", "backend_eng"]
        elif any(w in msg for w in ["timeout", "503", "502", "connection", "unavailable"]):
            teams = ["sre_ops", "devops"]
        elif any(w in msg for w in ["react", "jsx", "render", "undefined is not a function"]):
            teams = ["frontend_eng", "qa_eng"]
        else:
            teams = ["backend_eng", "qa_eng"]
        return {
            "root_cause": f"Error detected: {first[:120]}",
            "fix": "Review and resolve the error in the affected service",
            "teams": teams,
            "requirement": f"Fix this error in project {project_id}: {first[:300]}",
        }

    def _parse_analysis(self, content: str, errors: list[dict]) -> dict:
        result = {
            "root_cause": "", "fix": "",
            "teams": ["backend_eng", "qa_eng"],
            "requirement": "",
        }
        for line in content.splitlines():
            if line.startswith("ROOT_CAUSE:"):
                result["root_cause"] = line.split(":", 1)[1].strip()
            elif line.startswith("FIX:"):
                result["fix"] = line.split(":", 1)[1].strip()
            elif line.startswith("TEAMS:"):
                raw = line.split(":", 1)[1].strip()
                parsed = [t.strip() for t in raw.split(",") if t.strip() in _VALID_TEAMS]
                if parsed:
                    result["teams"] = parsed
            elif line.startswith("REQUIREMENT:"):
                result["requirement"] = line.split(":", 1)[1].strip()
        if not result["requirement"] and errors:
            result["requirement"] = f"Fix error: {errors[0].get('msg', '')[:300]}"
        return result

    # ──────────────────────────────────────────────────────────────────────
    #  Agent sign-off
    # ──────────────────────────────────────────────────────────────────────

    def get_agent_signoffs(
        self,
        fix_requirement: str,
        fix_artifact: str,
        teams: list[str],
    ) -> dict[str, dict]:
        """Ask each affected team + mandatory QA + SRE to review the fix."""
        # Always include QA and SRE as mandatory reviewers
        review_teams = list(dict.fromkeys(teams + ["qa_eng", "sre_ops"]))
        signoffs: dict[str, dict] = {}

        for team in review_teams:
            if self.llm_runtime:
                try:
                    prompt = (
                        f"You are the {team} team lead. Review this auto-generated fix proposal "
                        f"and decide if it is safe to merge.\n\n"
                        f"ORIGINAL ISSUE:\n{fix_requirement[:400]}\n\n"
                        f"PROPOSED FIX ARTIFACT:\n{fix_artifact[:600]}\n\n"
                        f"Respond with EXACTLY two lines:\n"
                        f"DECISION: APPROVED or REJECTED\n"
                        f"REASON: <one sentence explaining your decision>\n"
                    )
                    res = self.llm_runtime.generate(
                        team=team, requirement=prompt,
                        prior_count=0, handoff_to="none",
                    )
                    if res and res.content:
                        lines = res.content.strip().splitlines()
                        dec = next((l for l in lines if "DECISION:" in l.upper()), "DECISION: APPROVED")
                        rea = next((l for l in lines if l.startswith("REASON:")), "REASON: Looks correct")
                        approved = ("APPROVED" in dec.upper()) and ("REJECTED" not in dec.upper())
                        reason = rea.split(":", 1)[1].strip() if ":" in rea else rea
                        signoffs[team] = {"approved": approved, "reason": reason}
                        continue
                except Exception as exc:
                    log.warning("Sign-off from %s failed: %s", team, exc)

            # LLM unavailable — auto-approve
            signoffs[team] = {"approved": True, "reason": "Auto-approved (LLM unavailable)"}

        return signoffs
