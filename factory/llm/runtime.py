import logging
import os
from dataclasses import dataclass
from typing import Any

import httpx

log = logging.getLogger(__name__)


@dataclass
class LLMGeneration:
    content: str
    source: str
    estimated_cost_usd: float
    budget_remaining_usd: float


# ── Per-team LLM prompts ──────────────────────────────────────────────────────
# These prompts ask the LLM to generate real, requirement-specific content.
# The output is used as the primary content for the team's deliverable.
_TEAM_PROMPTS: dict[str, str] = {
    "product_mgmt": (
        "You are a product manager. Write a concise PRD for this requirement:\n{requirement}\n\n"
        "Include: Goals, User Stories (3-5), Success Metrics, Out-of-scope. Plain text, no markdown headers."
    ),
    "biz_analysis": (
        "You are a business analyst. Write acceptance criteria for:\n{requirement}\n\n"
        "Format: Given/When/Then. 4-6 criteria. Plain text."
    ),
    "solution_arch": (
        "You are a software architect. Describe the system architecture for:\n{requirement}\n\n"
        "Include: Components, Data flow, Tech choices, Key decisions. Concise, technical."
    ),
    "api_design": (
        "You are an API designer. Design the REST API for:\n{requirement}\n\n"
        "List each endpoint: METHOD /path — description. Include request/response shapes."
    ),
    "ux_ui": (
        "You are a UX designer. Describe the user interface and flow for:\n{requirement}\n\n"
        "Include: Screens, Navigation flow, Key interactions, UI principles."
    ),
    "frontend_eng": (
        "You are an expert React developer. Generate a COMPLETE, SELF-CONTAINED, FULLY WORKING React component "
        "that implements this requirement:\n\n{requirement}\n\n"
        "CRITICAL RULES:\n"
        "- Single component named `App` with ALL logic and UI inside it\n"
        "- Use React 18 hooks (useState, useEffect, useMemo, etc.)\n"
        "- Do NOT import from any external files or npm packages except React\n"
        "- Must run with React 18 + ReactDOM loaded from CDN + Babel standalone (no bundler)\n"
        "- Include ALL business logic (calculations, conversions, data, etc.) inline\n"
        "- Modern, clean UI with inline styles or a simple <style> block above the component\n"
        "- For a calculator/converter: implement all the actual math/conversion logic\n"
        "- Return ONLY the raw JavaScript/JSX code.\n"
        "- ABSOLUTELY NO markdown code fences (```) — no ```javascript, no ```jsx, no ``` at all.\n"
        "- NO import statements. NO export statements. Just plain function/const declarations."
    ),
    "backend_eng": (
        "You are an expert FastAPI/Python developer. Generate a complete, working FastAPI application for:\n\n"
        "{requirement}\n\n"
        "Include all imports, Pydantic models, and endpoint implementations with real logic (not placeholders). "
        "Return ONLY raw Python code. ABSOLUTELY NO markdown fences (```)."
    ),
    "database_eng": (
        "You are a database engineer. Write the SQL schema (PostgreSQL) for:\n{requirement}\n\n"
        "Include: CREATE TABLE statements, indexes, constraints. Return only SQL."
    ),
    "data_eng": (
        "You are a data engineer. Write a Python ETL pipeline for:\n{requirement}\n\n"
        "Include extract, transform, load functions with real logic. Return only Python code."
    ),
    "ml_eng": (
        "You are an ML engineer. Describe the ML approach and write pseudocode/Python for:\n{requirement}\n\n"
        "Include: Problem framing, Model choice, Training approach, Evaluation metrics."
    ),
    "security_eng": (
        "You are a security engineer. Write a threat model and security controls for:\n{requirement}\n\n"
        "Include: STRIDE threats, mitigations, and priority controls."
    ),
    "compliance": (
        "You are a compliance officer. Write compliance requirements for:\n{requirement}\n\n"
        "Include: Applicable standards, required controls, evidence needed."
    ),
    "devops": (
        "You are a DevOps engineer. Write a Dockerfile + GitHub Actions CI/CD pipeline for:\n{requirement}\n\n"
        "Return as two code blocks: Dockerfile, then .github/workflows/ci.yaml"
    ),
    "qa_eng": (
        "You are a QA engineer. Write a comprehensive test plan for:\n{requirement}\n\n"
        "Include: Test strategy, 8-10 specific test cases with steps and expected results."
    ),
    "sre_ops": (
        "You are an SRE. Write SLO definitions and alerting rules for:\n{requirement}\n\n"
        "Include: SLOs (availability, latency, error rate), Prometheus alert rules, runbook links."
    ),
    "docs_team": (
        "You are a technical writer. Write a README and user guide for:\n{requirement}\n\n"
        "Include: Overview, Quick start, Usage examples, API reference."
    ),
    "feature_eng": (
        "You are a feature engineer. Write a feature delivery summary for:\n{requirement}\n\n"
        "Include: Features delivered, story points, sprint plan, open items."
    ),
}


class TeamLLMRuntime:
    """Best-effort LiteLLM proxy runtime with per-team spend limits.

    Falls back cleanly when disabled, proxy is unavailable, or budget is exhausted.
    """

    TEAM_MODEL = {
        "product_mgmt": "factory/architect",
        "biz_analysis": "factory/architect",
        "solution_arch": "factory/architect",
        "api_design": "factory/coder",
        "ux_ui": "factory/fast",
        "frontend_eng": "factory/coder",
        "backend_eng": "factory/coder",
        "database_eng": "factory/coder",
        "data_eng": "factory/cheap",
        "ml_eng": "factory/cheap",
        "security_eng": "factory/architect",
        "compliance": "factory/architect",
        "devops": "factory/coder",
        "qa_eng": "factory/fast",
        "sre_ops": "factory/fast",
        "docs_team": "factory/cheap",
        "feature_eng": "factory/fast",
    }
    AVAILABLE_MODELS = [
        # Factory aliases (routed via LiteLLM proxy)
        "factory/architect",
        "factory/coder",
        "factory/fast",
        "factory/cheap",
        # Google Gemini
        "gemini/gemini-2.0-flash",
        "gemini/gemini-2.5-pro-preview-06-05",
        "gemini/gemini-2.5-flash-preview-05-20",
        # OpenAI
        "openai/gpt-4o",
        "openai/gpt-4o-mini",
        "openai/gpt-4.1",
        "openai/o3-mini",
        # Anthropic
        "anthropic/claude-sonnet-4-20250514",
        "anthropic/claude-3-5-haiku-20241022",
        # AWS Bedrock
        "bedrock/anthropic.claude-sonnet-4-20250514-v1:0",
        "bedrock/amazon.nova-pro-v1:0",
        # Azure OpenAI
        "azure/gpt-4o",
        "azure/gpt-4o-mini",
    ]

    def __init__(self) -> None:
        self.enabled = os.getenv("ENABLE_LLM_RUNTIME", "false").lower() == "true"
        self.proxy_url = os.getenv("LITELLM_PROXY_URL", "http://litellm:4000").rstrip("/")
        self._spent_by_team: dict[str, float] = {}
        self._limit_by_team = self._parse_team_limits(os.getenv("TEAM_BUDGETS_USD", ""))
        self._api_key_by_team: dict[str, str] = {}

    @staticmethod
    def _parse_team_limits(raw: str) -> dict[str, float]:
        if not raw.strip():
            return {}
        result: dict[str, float] = {}
        for pair in raw.split(","):
            if ":" not in pair:
                continue
            team, value = pair.split(":", 1)
            team = team.strip()
            try:
                result[team] = max(0.0, float(value.strip()))
            except ValueError:
                continue
        return result

    def _team_limit(self, team: str) -> float:
        return self._limit_by_team.get(team, float(os.getenv("DEFAULT_TEAM_BUDGET_USD", "0.50")))

    def spent(self, team: str) -> float:
        return self._spent_by_team.get(team, 0.0)

    def remaining(self, team: str) -> float:
        return max(0.0, self._team_limit(team) - self.spent(team))

    def governance_snapshot(self) -> dict[str, Any]:
        teams = sorted(set(self.TEAM_MODEL.keys()) | set(self._limit_by_team.keys()) | set(self._spent_by_team.keys()))
        return {
            "enabled": self.enabled,
            "proxy_url": self.proxy_url,
            "available_models": self.AVAILABLE_MODELS,
            "teams": {
                team: {
                    "limit_usd": round(self._team_limit(team), 6),
                    "spent_usd": round(self.spent(team), 6),
                    "remaining_usd": round(self.remaining(team), 6),
                    "model": self.TEAM_MODEL.get(team, "factory/cheap"),
                    "api_key": self._mask_key(self._api_key_by_team.get(team, "")),
                    "has_custom_key": team in self._api_key_by_team,
                }
                for team in teams
            },
        }

    @staticmethod
    def _mask_key(key: str) -> str:
        """Return a masked version of an API key for safe display."""
        if not key:
            return ""
        if len(key) <= 8:
            return "*" * len(key)
        return key[:4] + "*" * (len(key) - 8) + key[-4:]

    def update_team_config(
        self,
        team: str,
        model: str | None = None,
        budget_usd: float | None = None,
        api_key: str | None = None,
    ) -> dict[str, Any]:
        if model is not None:
            if model not in self.AVAILABLE_MODELS and "/" not in model:
                raise ValueError(f"Unsupported model: {model}. Use provider/model format (e.g. openai/gpt-4o).")
            self.TEAM_MODEL[team] = model
        if budget_usd is not None:
            self._limit_by_team[team] = max(0.0, float(budget_usd))
        if api_key is not None:
            if api_key.strip():
                self._api_key_by_team[team] = api_key.strip()
            else:
                self._api_key_by_team.pop(team, None)

        return {
            "team": team,
            "model": self.TEAM_MODEL.get(team, "factory/cheap"),
            "limit_usd": round(self._team_limit(team), 6),
            "spent_usd": round(self.spent(team), 6),
            "remaining_usd": round(self.remaining(team), 6),
            "has_custom_key": team in self._api_key_by_team,
        }

    @staticmethod
    def _estimate_cost_usd(text_chars: int) -> float:
        # Conservative coarse estimate for governance-only checks.
        return max(0.001, (text_chars / 1000.0) * 0.003)

    def generate(self, team: str, requirement: str, prior_count: int, handoff_to: str) -> LLMGeneration | None:
        if not self.enabled:
            return None

        # Use team-specific prompt if available, otherwise generic
        prompt_template = _TEAM_PROMPTS.get(team, (
            "You are a {team} specialist. Produce the key deliverable for this requirement:\n"
            "{requirement}\n\nBe specific and practical. prior_context_items={prior_count}."
        ))
        prompt = prompt_template.format(
            team=team,
            requirement=requirement,
            prior_count=prior_count,
            handoff_to=handoff_to,
        )

        estimate = self._estimate_cost_usd(len(prompt))
        if self.remaining(team) < estimate:
            return None

        model = self.TEAM_MODEL.get(team, "factory/cheap")
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": "You are a specialist software delivery assistant. Return exactly what is asked — no preamble, no explanation, just the deliverable content."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.3,
            "max_tokens": 2000,
        }

        content: str | None = None
        source = f"litellm-proxy:{model}"

        # ── Tier 1: LiteLLM proxy ────────────────────────────────────────────
        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.post(
                    f"{self.proxy_url}/chat/completions", json=payload
                )
                response.raise_for_status()
                data = response.json()
            content = (
                data.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
                .strip()
            ) or None
        except Exception as _e1:
            log.debug("Proxy call failed for team=%s, trying SDK: %s", team, _e1)

        # ── Tier 2: LiteLLM SDK direct (bypasses proxy, uses provider directly) ──
        if content is None:
            try:
                import litellm  # type: ignore[import]
                extra: dict = {}
                if team in self._api_key_by_team:
                    extra["api_key"] = self._api_key_by_team[team]
                sdk_resp = litellm.completion(
                    model=model,
                    messages=payload["messages"],
                    temperature=0.3,
                    max_tokens=2000,
                    **extra,
                )
                content = (sdk_resp.choices[0].message.content or "").strip() or None
                source = f"litellm-sdk:{model}"
            except Exception as _e2:
                log.debug("LiteLLM SDK failed for team=%s, trying Ollama: %s", team, _e2)

        # ── Tier 3: Ollama local model ────────────────────────────────────────
        if content is None:
            try:
                ollama_url = os.getenv("OLLAMA_URL", "http://ollama:11434").rstrip("/")
                ollama_model = os.getenv("OLLAMA_MODEL", "llama3.2")
                with httpx.Client(timeout=60.0) as client:
                    response = client.post(
                        f"{ollama_url}/api/chat",
                        json={
                            "model": ollama_model,
                            "messages": payload["messages"],
                            "stream": False,
                            "options": {"temperature": 0.3, "num_predict": 2000},
                        },
                    )
                    response.raise_for_status()
                    data = response.json()
                content = (data.get("message", {}).get("content", "") or "").strip() or None
                source = f"ollama:{ollama_model}"
            except Exception as _e3:
                log.debug("Ollama fallback failed for team=%s: %s", team, _e3)

        if not content:
            return None

        self._spent_by_team[team] = self.spent(team) + estimate
        return LLMGeneration(
            content=content,
            source=source,
            estimated_cost_usd=estimate,
            budget_remaining_usd=self.remaining(team),
        )
