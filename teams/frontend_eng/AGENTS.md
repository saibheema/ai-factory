# Frontend Engineering Team — AGENTS

Operatives:
- **Lead Frontend Engineer** — owns the App component tree, routing, and state management architecture
- **Component Builder** — implements individual UI components using the chosen component library
- **API Integration Engineer** — wires fetch/axios calls to API contract endpoints with error handling
- **State Manager** — implements global state (Zustand/Redux Toolkit/TanStack Query) and data flow
- **E2E Test Author** — writes Playwright tests covering all user flows from the UX spec
- **Accessibility Engineer** — ensures keyboard navigation, ARIA roles, focus management, color contrast
- **Performance Engineer** — monitors bundle size, LCP, CLS, INP — optimizes where needed
- **GitHub PR Author** — opens PRs with conventional commits, links to Plane stories

Handoff Protocol:
  Lead Frontend Engineer pushes src/ to Git branch `ai-factory/{project}/frontend_eng`.
  Playwright E2E must PASS before handoff.
  Backend Eng receives API integration spec via Slack (which endpoints FE calls + expected shapes).
