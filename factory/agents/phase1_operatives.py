from dataclasses import dataclass


@dataclass
class OperativeOutput:
    team: str
    artifact: str
    summary: str


def biz_analysis_operative(requirement: str) -> OperativeOutput:
    artifact = (
        f"BRD:\n"
        f"- problem: {requirement}\n"
        f"- scope: phase1-mvp\n"
        f"- acceptance: deliver 5-stage run"
    )
    return OperativeOutput(team="biz_analysis", artifact=artifact, summary="Requirement structured")


def solution_arch_operative(requirement: str, ba_artifact: str) -> OperativeOutput:
    artifact = (
        f"ARCH:\n"
        f"- requirement: {requirement}\n"
        f"- inputs: BA ready={bool(ba_artifact)}\n"
        f"- stack: fastapi+redis+postgres+cloudrun"
    )
    return OperativeOutput(team="solution_arch", artifact=artifact, summary="Architecture drafted")


def backend_eng_operative(requirement: str, arch_artifact: str) -> OperativeOutput:
    artifact = (
        "API-SPEC:\n"
        "- POST /api/pipelines/core/run\n"
        "- POST /api/projects/{id}/ask\n"
        f"- based_on_arch: {arch_artifact.splitlines()[0] if arch_artifact else 'n/a'}"
    )
    return OperativeOutput(team="backend_eng", artifact=artifact, summary="API contract synthesized")


def qa_eng_operative(api_artifact: str) -> OperativeOutput:
    artifact = (
        "QA-PLAN:\n"
        "- test health endpoints\n"
        "- test core run stages==5\n"
        "- test clarification timeout and roundtrip\n"
        f"- api_ref: {api_artifact.splitlines()[0] if api_artifact else 'n/a'}"
    )
    return OperativeOutput(team="qa_eng", artifact=artifact, summary="QA checks prepared")


def docs_team_operative(requirement: str, qa_artifact: str) -> OperativeOutput:
    artifact = (
        "DOCS:\n"
        f"- requirement: {requirement}\n"
        "- quickstart: deploy + health + smoke\n"
        f"- validation: {qa_artifact.splitlines()[1] if qa_artifact else 'n/a'}"
    )
    return OperativeOutput(team="docs_team", artifact=artifact, summary="Runbook summary generated")
