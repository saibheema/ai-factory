# QA Engineering Team — TOOLS

Test Automation:
- **pytest**: Unit + integration tests — must pass >=80% coverage
- **Playwright**: E2E browser tests + WCAG 2.1 AA accessibility checks
- **k6**: Load tests (smoke + sustained) to validate SLO latency targets
- **Sandbox**: Run tests in isolated environment

Static Validation:
- Python syntax check (compile()) on all generated .py files
- JSX/JS component validation (function declarations, root component presence)
- Dockerfile validation (FROM instruction, non-root user)
- Markdown fence marker detection in generated code files

Data Validation:
- **SQL Tool**: Validate backend ORM queries against Database Eng schema
- **CSV**: Import test datasets for data-driven test cases

Documentation:
- **Google Sheets**: Test Plan & Cases (TC-ID, category, steps, expected, priority, status)
- **Git** (push): Test automation code to tests/ in project branch
- **GCS**: Store test reports and coverage artifacts

Tracking:
- **Plane**: Test failure issues linked to originating team's Plane story

Notifications:
- **Slack**: #qa channel — QA verdict (PASS/FAIL) with failure count and links
- **Notification**: Stage-complete broadcast to SRE Ops with load test results
