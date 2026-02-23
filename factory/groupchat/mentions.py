"""Group-chat @mention routing helpers.

``TEAM_ALIASES`` maps common user-typed shorthands (case-insensitive) to the
canonical team identifiers used throughout the pipeline.

``parse_mentions`` extracts canonical team names from @-tagged tokens in a
string, enabling smart routing so only the tagged agent(s) respond when a
user writes e.g. ``@solArch what was your decision on the DB schema?``
"""
import re

# Alias map: normalised lowercase shorthand → canonical team name.
TEAM_ALIASES: dict[str, str] = {
    # Solution Architecture
    "solarch": "solution_arch", "sol_arch": "solution_arch", "solution_arch": "solution_arch",
    "arch": "solution_arch", "architect": "solution_arch",
    # Backend
    "backend": "backend_eng", "backend_eng": "backend_eng", "be": "backend_eng",
    # Frontend
    "frontend": "frontend_eng", "frontend_eng": "frontend_eng", "fe": "frontend_eng", "ui": "frontend_eng",
    # Product / Biz
    "pm": "product_mgmt", "product": "product_mgmt", "product_mgmt": "product_mgmt",
    "ba": "biz_analysis", "biz": "biz_analysis", "biz_analysis": "biz_analysis",
    # API Design
    "api": "api_design", "api_design": "api_design",
    # UX / UI
    "ux": "ux_ui", "ux_ui": "ux_ui", "design": "ux_ui",
    # Database
    "db": "database_eng", "database": "database_eng", "database_eng": "database_eng",
    # Data / ML
    "data": "data_eng", "data_eng": "data_eng",
    "ml": "ml_eng", "ml_eng": "ml_eng",
    # Security / Compliance
    "security": "security_eng", "security_eng": "security_eng", "sec": "security_eng",
    "compliance": "compliance",
    # DevOps / SRE
    "devops": "devops", "ops": "devops",
    "sre": "sre_ops", "sre_ops": "sre_ops",
    # QA
    "qa": "qa_eng", "qa_eng": "qa_eng", "test": "qa_eng",
    # Docs / Features
    "docs": "docs_team", "docs_team": "docs_team",
    "feature": "feature_eng", "features": "feature_eng", "feature_eng": "feature_eng",
}


def parse_mentions(text: str) -> list[str]:
    """Extract canonical team names from @mention tokens in text.

    Supports: @solArch, @backend, @qa_eng, @ml, etc.
    Returns a deduplicated list in order of first appearance; empty list if none.
    """
    found: list[str] = []
    seen: set[str] = set()
    for token in re.findall(r"@([A-Za-z0-9_]+)", text):
        canonical = TEAM_ALIASES.get(token.lower())
        if canonical and canonical not in seen:
            found.append(canonical)
            seen.add(canonical)
    return found
