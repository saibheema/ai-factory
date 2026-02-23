# QA Engineering Team — AGENTS

Operatives:
- **Test Plan Author** — maps every acceptance criterion from Biz Analysis to a test case with steps
- **Static Validator** — checks all generated code for syntax errors, fence markers, missing exports
- **API Test Engineer** — writes pytest tests for every OpenAPI endpoint (happy path + negative cases)
- **E2E Test Engineer** — writes Playwright browser tests for all user flows from UX spec
- **Load Test Engineer** — writes k6 scripts for p99 latency + error rate validation
- **Accessibility Tester** — runs WCAG 2.1 AA checks on frontend output
- **SQL Test Engineer** — validates backend ORM queries against Database Eng schema
- **QA Verdict Publisher** — compiles PASS/FAIL verdict with issue list, publishes to Plane + Slack

Handoff Protocol:
  Test plan published in Google Sheets.
  Test automation code pushed to Git.
  k6 load test must meet SRE Ops SLO before passing.
  SRE Ops receives QA report + load test results for production readiness sign-off.
