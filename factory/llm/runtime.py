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
        "You are a Principal Solutions Architect and Technical Lead. "
        "Your output is the SINGLE SOURCE OF TRUTH that every downstream team (API design, UX/UI, "
        "Frontend, Backend, Database, DevOps, Security) will build upon.\n\n"
        "REQUIREMENT:\n{requirement}\n\n"
        "Perform DEEP RESEARCH and produce a comprehensive Architecture Decision Record (ADR) covering:\n\n"
        "1. UI/FRONTEND TECH STACK\n"
        "   - Evaluate: React 18+Vite, Next.js 14 (App Router), Vue 3+Nuxt, SvelteKit, Angular 17\n"
        "   - Choose ONE with full justification (DX, performance, SSR/SSG needs, ecosystem maturity)\n"
        "   - State: component library (Shadcn/UI, MUI, Ant Design, Radix, Tailwind), state management \n"
        "     (Zustand, Jotai, Redux Toolkit, TanStack Query), styling approach\n\n"
        "2. BACKEND TECH STACK\n"
        "   - Evaluate: FastAPI+Python 3.12, Node/NestJS, Go/Gin, Django REST Framework\n"
        "   - Choose ONE with justification (async needs, type safety, team familiarity, performance)\n"
        "   - State: ORM/query layer, validation, auth middleware, async/sync patterns\n\n"
        "3. DATABASE & STORAGE\n"
        "   - Primary DB: PostgreSQL 16 vs MySQL 8 vs MongoDB 7 vs CockroachDB (choose + justify)\n"
        "   - Cache layer: Redis 7 vs Memcached (choose + justify)\n"
        "   - Object storage: GCS vs S3 (choose + justify)\n"
        "   - Search/vector: pgvector vs Elasticsearch vs Typesense (if requirement needs it)\n\n"
        "4. CLOUD & INFRASTRUCTURE\n"
        "   - Deployment target: Cloud Run vs GKE vs ECS Fargate vs Lambda (choose + justify)\n"
        "   - IaC: Terraform vs Pulumi (choose + justify)\n"
        "   - CI/CD: GitHub Actions vs Cloud Build (choose + justify)\n\n"
        "5. API DESIGN APPROACH\n"
        "   - Protocol: REST vs GraphQL vs tRPC vs gRPC (choose + justify)\n"
        "   - Auth: JWT+OAuth2 vs OIDC vs API keys (choose + justify)\n"
        "   - Versioning: URI path vs headers vs query param\n\n"
        "6. INTEGRATION & MESSAGING (only if async needed)\n"
        "   - Sync vs async; if async: Pub/Sub vs Kafka vs Redis Streams\n\n"
        "7. CROSS-CUTTING CONCERNS\n"
        "   - Observability stack: traces (OTEL), metrics (Prometheus), logs (structured JSON)\n"
        "   - Security posture: RBAC, secret manager, WAF, CSP headers\n"
        "   - Scalability: horizontal auto-scaling strategy, CDN, caching layers\n\n"
        "FORMAT YOUR RESPONSE EXACTLY as follows:\n"
        "ADR-001: [Title matching the requirement]\n"
        "STATUS: Accepted\n"
        "CONTEXT: [2-3 sentences — problem + constraints]\n\n"
        "DECISIONS:\n"
        "- UI Stack: [chosen framework + component lib + state mgmt + styling]\n"
        "- Backend: [chosen framework + ORM + auth + async pattern]\n"
        "- Database: [primary DB + cache + storage + search if needed]\n"
        "- Cloud/Infra: [deployment + IaC + CI/CD]\n"
        "- API Protocol: [REST/GraphQL/tRPC + auth + versioning]\n"
        "- Messaging: [sync/async + broker if needed]\n"
        "- Observability: [tracing + metrics + logging tools]\n\n"
        "TECH STACK SUMMARY (one line all teams must follow):\n"
        "[e.g. Next.js 14 | FastAPI 0.115 | PostgreSQL 16 | Redis 7 | Cloud Run | REST+JWT]\n\n"
        "CONSEQUENCES:\n"
        "- Positive: [list 3-4 benefits]\n"
        "- Risks: [list 2-3 risks + mitigations]\n\n"
        "HANDOFF_API_DESIGN: [specific OpenAPI contract instructions, auth scheme, versioning]\n"
        "HANDOFF_UX_UI: [specific UI framework, component library, design system, accessibility standard]\n"
        "HANDOFF_FRONTEND_ENG: [framework + component lib + state management + build tool + routing]\n"
        "HANDOFF_BACKEND_ENG: [framework + ORM + async pattern + auth middleware + env config]\n"
        "HANDOFF_DATABASE_ENG: [DB engine + migration tool + naming conventions + index strategy]\n"
        "HANDOFF_DEVOPS: [container base image + cloud target + IaC tool + secret manager + scaling]\n"
        "HANDOFF_SECURITY_ENG: [auth mechanism + threat surface + OWASP priorities + scan tools]"
    ),
    "api_design": (
        "You are a contract-first API Designer. The upstream Solution Architect has already chosen "
        "the API protocol and auth scheme — extract those decisions from the requirement context below "
        "and apply them exactly.\n\n"
        "REQUIREMENT + UPSTREAM CONTEXT:\n{requirement}\n\n"
        "Design a complete API contract following the Sol Arch decisions. Include:\n"
        "1. OpenAPI 3.0 metadata (title, version, servers, security schemes)\n"
        "2. All resource endpoints (GROUP by resource): METHOD /path — summary — request body — responses\n"
        "3. Auth flow: how tokens are obtained and validated\n"
        "4. Error response schema (RFC 7807 Problem+JSON)\n"
        "5. Pagination strategy for list endpoints\n"
        "6. Versioning: base path prefix\n"
        "HANDOFF_FRONTEND_ENG: [list endpoint URLs the frontend will call + expected shapes]\n"
        "HANDOFF_BACKEND_ENG: [route handler signatures, auth middleware placement, validation rules]"
    ),
    "ux_ui": (
        "You are a Senior UX/UI Designer. The Solution Architect has chosen the UI framework and "
        "component library — use those decisions from the context below.\n\n"
        "REQUIREMENT + UPSTREAM CONTEXT:\n{requirement}\n\n"
        "Produce a complete UX specification including:\n"
        "1. USER FLOWS: step-by-step flows for all primary personas (authenticated, admin, guest)\n"
        "2. SCREEN INVENTORY: list every screen/page with its purpose and key components\n"
        "3. COMPONENT MAP: which component library components map to each UI element\n"
        "4. DESIGN TOKENS: exact values — colors (primary, surface, error), typography (font, scale), \n"
        "   spacing (base-4 scale), border-radius, shadow elevation\n"
        "5. ACCESSIBILITY: WCAG 2.1 AA requirements per screen\n"
        "6. STATE PATTERNS: loading, empty, error, success states for each major screen\n"
        "HANDOFF_FRONTEND_ENG: [component breakdown per screen, exact design tokens, interaction specs]\n"
        "HANDOFF_API_DESIGN: [data shape needed per screen — fields, sorting, filtering requirements]"
    ),
    "frontend_eng": (
        "You are an expert Frontend Engineer. The Solution Architect defined the UI framework + component "
        "library + state management. The UX/UI team defined screen layouts, design tokens, and component map. "
        "The API Design team defined endpoint contracts. Extract all these from the context below and "
        "implement accordingly.\n\n"
        "REQUIREMENT + UPSTREAM CONTEXT:\n{requirement}\n\n"
        "Generate a COMPLETE, SELF-CONTAINED, FULLY WORKING React component implementing this requirement.\n\n"
        "CRITICAL RULES:\n"
        "- Single component named `App` with ALL logic and UI inside it\n"
        "- Use React 18 hooks (useState, useEffect, useMemo, useCallback)\n"
        "- Apply the design tokens from UX/UI spec (colors, spacing, typography)\n"
        "- Wire up to the API endpoints defined by API Design team (use fetch/axios pattern)\n"
        "- Handle ALL states: loading, empty, error, success (as per UX spec)\n"
        "- Do NOT import from any external files or npm packages except React\n"
        "- Must run with React 18 + ReactDOM loaded from CDN + Babel standalone (no bundler)\n"
        "- Include ALL business logic inline\n"
        "- Modern, clean UI applying upstream design tokens via inline styles or <style> block\n"
        "- Return ONLY the raw JavaScript/JSX code.\n"
        "- ABSOLUTELY NO markdown code fences (```) — no ```javascript, no ```jsx, no ``` at all.\n"
        "- NO import statements. NO export statements. Just plain function/const declarations."
    ),
    "backend_eng": (
        "You are an expert Backend Engineer. The Solution Architect chose the framework, ORM, and auth pattern. "
        "The API Design team wrote the OpenAPI contract. The Database team will own the schema. "
        "Extract all these decisions from the context below and implement accordingly.\n\n"
        "REQUIREMENT + UPSTREAM CONTEXT:\n{requirement}\n\n"
        "Generate a COMPLETE, production-quality FastAPI application that:\n"
        "1. Implements ALL endpoints from the API contract (exact paths, methods, request/response shapes)\n"
        "2. Uses Pydantic v2 models for all request/response validation\n"
        "3. Implements the auth middleware chosen by Sol Arch (JWT/OAuth2)\n"
        "4. Uses async SQLAlchemy (or the ORM Sol Arch specified) for DB operations\n"
        "5. Includes proper error handling (HTTPException with RFC 7807 detail)\n"
        "6. Adds /health and /ready endpoints for Cloud Run\n"
        "7. Structured logging (JSON) for the observability stack\n"
        "Include all imports, models, routers, and middleware. "
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

    # Teams that generate code files — need special follow-up handling
    _CODE_TEAMS = frozenset({"frontend_eng", "backend_eng", "database_eng", "data_eng", "ml_eng", "devops", "qa_eng"})

    def generate(self, team: str, requirement: str, prior_count: int, handoff_to: str) -> LLMGeneration | None:
        if not self.enabled:
            return None

        # Detect follow-up / incremental update mode
        is_followup = "=== EXISTING PROJECT CODE" in requirement

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

        # Build system prompt — incremental mode for follow-up code generations
        if is_followup and team in self._CODE_TEAMS:
            system_content = (
                "You are a specialist software delivery assistant working on an INCREMENTAL UPDATE.\n"
                "The existing code is provided in the requirement between '=== EXISTING PROJECT CODE ===' markers.\n"
                "RULES:\n"
                "1. EXTEND and MODIFY the existing code — do NOT rewrite it from scratch.\n"
                "2. Preserve ALL existing functionality — only add or change what the new requirement specifies.\n"
                "3. Output the COMPLETE updated file(s), not diffs or partial code.\n"
                "4. Maintain the same coding style and structure as the existing code."
            )
        else:
            system_content = (
                "You are a specialist software delivery assistant. "
                "Return exactly what is asked — no preamble, no explanation, just the deliverable content."
            )

        # Architect-class teams need more tokens for deep research output
        _ARCHITECT_TEAMS = frozenset({"solution_arch", "security_eng", "compliance", "biz_analysis", "product_mgmt"})
        _CODER_TEAMS = frozenset({"frontend_eng", "backend_eng", "database_eng", "data_eng", "ml_eng", "devops", "api_design"})
        if team in _ARCHITECT_TEAMS:
            max_tokens = 4000
        elif team in _CODER_TEAMS:
            max_tokens = 3000
        else:
            max_tokens = 2000

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_content},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.3,
            "max_tokens": max_tokens,
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
                            "options": {"temperature": 0.3, "num_predict": max_tokens},
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
