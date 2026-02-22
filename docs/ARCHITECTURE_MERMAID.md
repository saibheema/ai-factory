# AI Software Factory — Mermaid Designs

This file contains standalone Mermaid diagrams for architecture, runtime flow, user workflow, and phased delivery.

## 0) How to View

- Open this file in VS Code.
- Use Markdown preview (Cmd+Shift+V) to render diagrams.
- If preview is split, use Cmd+K then V.

## 1) System Architecture (Layered)

```mermaid
flowchart TB
  subgraph UI[Frontend Layer]
    A[React Dashboard]
    B[Chainlit Chat]
    C[Group Chat UI]
  end

  subgraph ORCH[Orchestrator Layer]
    D[API Gateway / FastAPI]
    E[Pipeline Engine]
    F[Clarification Broker]
    G[HITL Bridge]
  end

  subgraph TEAM[Team Execution Layer]
    T1[Business Analysis Team]
    T2[Solution Architecture Team]
    T3[Engineering Teams]
    T4[QA/Security/Docs Teams]
  end

  subgraph MEM[Memory & Messaging]
    H[Memory Service]
    I[(PostgreSQL + pgvector)]
    J[(Redis Streams/PubSub)]
    K[Immutable Audit Memory]
  end

  subgraph LLM[Model Routing]
    L[LiteLLM SDK/Proxy]
    M[Cloud Models]
    N[Ollama Local Models]
  end

  subgraph OBS[Observability]
    O[Langfuse]
    P[Prometheus/Grafana]
    Q[Loki/OTEL]
  end

  A --> D
  B --> D
  C --> D
  D --> E
  E --> T1 --> T2 --> T3 --> T4
  E --> F
  F --> J
  E --> H
  H --> I
  H --> K
  T1 --> L
  T2 --> L
  T3 --> L
  T4 --> L
  L --> M
  L --> N
  D --> O
  E --> O
  E --> P
  E --> Q
```

## 2) Runtime Sequence (Objective Execution)

```mermaid
sequenceDiagram
  autonumber
  participant U as User
  participant FE as Dashboard/Chat
  participant API as Orchestrator API
  participant PIPE as Pipeline Engine
  participant TEAM as Team Operative
  participant MEM as Memory Service
  participant LLM as LiteLLM Router
  participant CLR as Clarification Broker
  participant HITL as HITL Service

  U->>FE: Submit requirement
  FE->>API: Create project/pipeline run
  API->>PIPE: Start stage
  PIPE->>MEM: Recall team + shared context
  PIPE->>TEAM: Execute objective
  TEAM->>LLM: Reason + tool calls
  LLM-->>TEAM: Response
  TEAM-->>PIPE: TaskResult
  alt NEEDS_CLARIFICATION
    PIPE->>CLR: Request clarification
    CLR-->>PIPE: Clarification response
  else BLOCKED/Timeout
    PIPE->>HITL: Escalate for human decision
    HITL-->>PIPE: Human input
  end
  PIPE->>MEM: Retain/consolidate + audit snapshot
  PIPE-->>API: Stage complete
  API-->>FE: Live status/events
  FE-->>U: Deliver artifact + trace summary
```

## 3) End-to-End User Workflow

```mermaid
flowchart LR
  U[User] --> S[Submit Requirement]
  S --> BA[Business Analysis]
  BA --> SA[Solution Architecture]
  SA --> ENG[Engineering Teams]
  ENG --> QA[QA + Security]
  QA --> DOC[Documentation]
  DOC --> R[Review Results]

  R -->|Approve| DONE[Complete / Release]
  R -->|Revise| BA

  ENG --> C{Need Clarification?}
  C -->|Yes| BR[Clarification Broker]
  BR --> TT[Target Team Reply]
  TT --> ENG
  BR -->|Timeout| H[HITL Decision]
  H --> ENG
```

## 4) Phase Delivery Timeline

```mermaid
gantt
  title AI Software Factory Delivery Plan
  dateFormat  YYYY-MM-DD
  axisFormat  %b %d

  section Phase 1 (Weeks 1–8)
  Infra Baseline + Core Services          :p1a, 2026-02-24, 14d
  Memory + Confidence Gates               :p1b, after p1a, 14d
  5-Team Pipeline + Basic UI              :p1c, after p1b, 28d

  section Phase 2 (Weeks 9–18)
  Expand to 17 Teams                      :p2a, after p1c, 21d
  Clarification Fabric + Group Chat       :p2b, after p2a, 21d
  Proxy Routing + Advanced Graph UI       :p2c, after p2b, 28d

  section Phase 3 (Weeks 19–26)
  Tool Matrix + CI Security               :p3a, after p2c, 21d
  Full Observability + Cost Controls      :p3b, after p3a, 21d
  Hardening + Release Readiness           :p3c, after p3b, 14d
```

## 5) Clarification Protocol State Flow

```mermaid
stateDiagram-v2
  [*] --> Running
  Running --> NeedsClarification: TaskResult.status=NEEDS_CLARIFICATION
  NeedsClarification --> Routed: Broker routes to target team
  Routed --> Resolved: Reply received within TTL
  Routed --> Escalated: TTL exceeded / hop limit
  Escalated --> Running: HITL response received
  Resolved --> Running: Objective resumed
  Running --> Blocked: TaskResult.status=BLOCKED
  Blocked --> Escalated
  Running --> Complete: TaskResult.status=COMPLETE
  Complete --> [*]
```

## 6) Container-Level Architecture (C4-style)

```mermaid
flowchart LR
  User[(User)]
  Browser[Web Browser]

  subgraph Platform[AI Software Factory Platform]
    Dashboard[React Dashboard]
    ChatUI[Chainlit UI]
    Api[Orchestrator API]
    Engine[Pipeline Engine]
    Clarify[Clarification Broker]
    MemorySvc[Memory Service]
    Hitl[HITL Service]
    Group[Group Chat Service]
    ModelRouter[LiteLLM Router]
  end

  subgraph Data[Data/Infra]
    PG[(PostgreSQL + pgvector)]
    Redis[(Redis Streams/PubSub)]
    Audit[(Immutable Audit Store)]
    Ollama[Ollama Local Models]
    Cloud[Cloud Models]
    Obs[Langfuse + Prometheus + Grafana + Loki]
  end

  User --> Browser --> Dashboard
  User --> Browser --> ChatUI
  Dashboard --> Api
  ChatUI --> Api
  Api --> Engine
  Engine --> Clarify
  Engine --> MemorySvc
  Engine --> Group
  Engine --> Hitl
  Engine --> ModelRouter
  Clarify --> Redis
  MemorySvc --> PG
  MemorySvc --> Redis
  MemorySvc --> Audit
  ModelRouter --> Ollama
  ModelRouter --> Cloud
  Api --> Obs
  Engine --> Obs
  MemorySvc --> Obs
```

## 7) Data Flow (Requirement to Release)

```mermaid
flowchart TD
  RQ[Requirement Submitted] --> V1[Validate Input + Create Project]
  V1 --> BA[Business Analysis Stage]
  BA --> SA[Solution Architecture Stage]
  SA --> FE[Feature/Frontend/Backend Stages]
  FE --> QA[QA + Security Validation]
  QA --> DOC[Documentation Packaging]
  DOC --> REL[Release Recommendation]

  BA --> MEM[(Memory Recall/Retain)]
  SA --> MEM
  FE --> MEM
  QA --> MEM
  DOC --> MEM

  FE --> G{Confidence Gate}
  G -->|COMPLETE| QA
  G -->|NEEDS_CLARIFICATION| CL[Clarification Loop]
  G -->|BLOCKED| HI[HITL Escalation]
  CL --> FE
  HI --> FE

  REL --> OUT[Artifacts + Trace + Audit Snapshot]
```
