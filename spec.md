# Project Sentinel Specification

## 1. Purpose

Project Sentinel is a production-grade internal intelligence system for a mid-sized company. It unifies official documents, GitHub knowledge, and Slack discussions into one secure internal product for employees and operators.

The system exists to solve the siloed-knowledge problem:

- official rules live in PDFs, handbooks, and process guides
- technical truth lives in repositories, runbooks, and internal docs
- recent decisions live in Slack channels and threads

Sentinel provides one secure answer surface while preserving departmental boundaries and evidence traceability.

## 2. Product Goals

### 2.1 Primary goals

- Provide fast, grounded answers to internal employee questions.
- Restrict retrieval to `user_department + shared` content only.
- Show source-backed evidence for every allowed answer.
- Surface conflicts between official and recent operational knowledge instead of hiding them.
- Give operators visibility into ingestion freshness, failures, and answer decisions.

### 2.2 Non-goals for v1

- Full microservices decomposition
- Complex document-level ACL models
- Advanced collaborative investigation workspaces
- Broad code-intelligence over every source file in every repository
- Locking all performance-sensitive techniques before benchmarks

## 3. Success Criteria

Sentinel should be evaluated across three dimensions.

### 3.1 User value

- Employees can ask one question instead of searching across multiple tools.
- Answers are useful enough to reduce manual follow-up in Slack or email.
- Saved sessions help users revisit earlier answers.

### 3.2 Answer quality

- Answer claims are traceable to retrieved evidence.
- Unsupported answers are refused instead of guessed.
- Source disagreement is presented honestly.
- Freshness signals are visible when a source may be stale.

### 3.3 Security and operations

- Cross-department leakage does not occur.
- Retrieval is scoped before answer synthesis.
- Connector freshness and failures are visible to admins.
- Audits explain why the system answered, split, or refused.

## 4. Users and Product Surfaces

### 4.1 Employee portal

Employees use an internal query workspace with:

- company-authenticated access
- secure question input
- saved personal sessions
- synthesized answers
- evidence view with citations and metadata
- refusal behavior for unsupported or restricted requests

### 4.2 Admin portal

Admins use an operations dashboard with:

- connector health by source and department
- freshness visibility
- sync history
- retry and pause controls
- audit access for decision tracing

## 5. Security Model

### 5.1 Identity

- Production identity model: enterprise SSO
- Request identity transport: JWT claims
- Required claim baseline: user identifier, department, role or privilege marker

### 5.2 Authorization

- V1 isolation boundary: department-level isolation plus shared content
- Allowed retrieval scope: only the caller's department and shared content
- Authorization must be enforced during retrieval, not after broad retrieval

### 5.3 Restricted requests

- Restricted questions must receive silent secure refusal
- Refusal must not reveal whether unauthorized content exists
- Unauthorized titles, excerpts, and metadata must not appear in answers or citations

## 6. Knowledge Domains

The simulated company includes:

- Engineering
- HR
- Sales
- Finance/Legal
- Shared company-wide content

Each source item must carry enough metadata to support retrieval, ranking, auditing, and traceability.

Required metadata baseline:

- source identifier
- parent item identifier
- department or shared visibility
- source type
- source title or label
- creation or publication timestamp when available
- last synced timestamp
- authority tier
- trace link back to origin

## 7. Source Types

Sentinel v1 supports real connectors for:

- PDFs and static document files
- GitHub repositories
- Slack channels and threads

### 7.1 Source role expectations

- PDFs are the high-authority baseline for official policy and process.
- GitHub contributes documentation and selected operational truth.
- Slack contributes recent operational context and decision signals.

### 7.2 Source conflict policy

When allowed sources disagree, the answer layer must not silently collapse them into a single forced conclusion. The employee experience must present:

- the official source position
- the recent operational discussion or update
- citations and timestamps for both tracks

This is the default dual-track conflict pattern.

## 8. Architecture

### 8.1 System style

- Backend framework: FastAPI
- Architecture style: modular monolith
- Frontend baseline: server-rendered internal portal using FastAPI templates
- Storage baseline: PostgreSQL with pgvector
- Background processing: asynchronous job runner for ingestion and scheduled sync tasks

### 8.2 Why PostgreSQL + pgvector is the v1 baseline

PostgreSQL + pgvector is the baseline because Sentinel is not only a vector search system. It must manage vectors alongside:

- source metadata
- access boundaries
- ingestion job state
- sync history
- session records
- citation traceability
- audit events

This keeps relational data and vector retrieval close together and reduces operational complexity in v1. This is a baseline choice, not an irreversible long-term commitment.

## 9. Internal System Modules

### 9.1 Identity and access module

Responsibilities:

- validate JWT claims
- construct request authorization context
- expose allowed retrieval scope

### 9.2 Source registry and ingestion module

Responsibilities:

- register approved sources
- execute source sync jobs
- normalize source content into a common internal model
- attach required metadata and trace links

### 9.3 Processing and indexing module

Responsibilities:

- transform normalized content into retrieval units
- persist embeddings and metadata
- preserve parent-source traceability
- support freshness-aware indexing

### 9.4 Retrieval module

Responsibilities:

- accept query plus auth scope
- perform scoped retrieval
- support metadata filtering
- rank results by relevance, authority, freshness, and source type
- return evidence sets suitable for grounded response generation

### 9.5 Answer orchestration module

Responsibilities:

- validate input
- request scoped evidence
- detect insufficient evidence
- synthesize conservative answers
- produce dual-track output when allowed sources conflict
- run output validation
- return refusal when necessary

### 9.6 Audit and operations module

Responsibilities:

- record request outcomes
- record which sources were considered
- record why the system answered, split, or refused
- expose operator-facing status and audit views

## 10. Normalized Internal Content Model

All source content must be normalized into one internal representation before indexing.

The normalized model must support:

- parent document, message thread, or repo file identity
- source-specific metadata
- department visibility
- freshness timestamps
- authority tier
- chunk or retrieval unit content
- traceability to the original source location

The model should preserve source-specific details where useful without forcing the rest of the system to understand every source format independently.

## 11. Retrieval and Answer Behavior

### 11.1 Retrieval scope

Each request is resolved with an authorization context first. Retrieval can only search content inside the allowed visibility set.

### 11.2 Retrieval unit

The primary retrieval unit is chunk-level content with strong parent-source traceability.

### 11.3 Ranking expectations

Ranking must be able to account for:

- semantic relevance
- source authority
- freshness
- source type
- agreement or disagreement across sources

### 11.4 Refusal behavior

The system must refuse when:

- evidence is insufficient
- the request targets unauthorized material
- output validation detects unacceptable leakage or unsupported content

### 11.5 Freshness behavior

If a source is stale but still usable, the system may answer from last indexed content. The response and admin experience must surface freshness risk explicitly.

## 12. Public Interfaces and Contracts

The specification requires the following interface categories.

### 12.1 Employee query flow

- start or continue a saved session
- submit a question
- receive an answer or refusal
- inspect evidence and source metadata

### 12.2 Admin operations flow

- inspect connector status
- inspect freshness and failures
- retry and pause sync jobs
- review audit traces

### 12.3 Connector contract

Each connector must define:

- how it authenticates
- what it syncs
- what metadata it emits
- how it reports sync state
- how it emits normalized content into the indexing pipeline

### 12.4 Answer response contract

Each answer response must be able to represent:

- final synthesis or refusal
- evidence citations
- freshness signals
- conflict sections when applicable
- session association

### 12.5 Audit event contract

Audit events must capture:

- caller identity context
- request summary
- retrieval scope
- considered evidence identifiers
- outcome type: answer, conflict split, or refusal
- relevant reason codes

## 13. Benchmark-Gated Decisions

The following items must remain open in the specification and later docs. They should be described by constraints and validation criteria rather than fixed implementation commitments:

- exact chunking strategy
- embedding model
- reranking approach
- hybrid retrieval strategy details
- ANN index strategy and tuning
- Slack thread grouping heuristics
- GitHub code-ingestion depth
- caching strategy
- whether orchestration remains plain service-layer Python or later adopts LangGraph

## 14. Validation Requirements

### 14.1 Product and UX scenarios

- Department-valid question returns a cited answer.
- Cross-department request receives a silent secure refusal.
- User continues an existing session successfully.
- PDF and Slack disagreement produces dual-track output.

### 14.2 Retrieval and grounding scenarios

- Retrieval never returns unauthorized content.
- Claims in answers are traceable to evidence.
- Freshness warnings appear when stale content is used.
- Allowed multi-source evidence can be combined in one answer.

### 14.3 Security and governance scenarios

- Unauthorized content does not appear in answer text, citations, or metadata.
- Admin-only audit views are not available to standard employees.
- Audit records explain answer, split, and refusal decisions.

### 14.4 Operational scenarios

- Failed sync jobs appear in the admin dashboard.
- Admins can retry and pause connectors.
- Freshness status updates by connector and department.
- Parent-source traceability survives ingestion and chunking.

## 15. Implementation Posture

Sentinel v1 should prefer simple, explainable architecture until benchmarks prove more complexity is necessary.

Guiding rules:

- lock structural decisions early
- keep performance-sensitive tactics benchmark-gated
- optimize for correctness before aggressiveness
- favor explicit traceability over hidden automation
- prefer operationally understandable behavior over framework novelty
