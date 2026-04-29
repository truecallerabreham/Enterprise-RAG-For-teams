# Project Sentinel Micro-Chunked Roadmap

This roadmap is the Phase 3 implementation plan derived from `spec.md`. Each chunk is intentionally narrow so the system can be built, tested, and reviewed one step at a time.

## Phase 3 Rules

- Work one chunk at a time.
- Define tests before implementation for each chunk.
- Do not merge multiple major concerns into one chunk.
- Preserve production-oriented traceability in every step.
- For every implementation chunk, explain the code from first principles before and after writing it so the reviewer can understand how and why it works instead of treating it like magic.
- Do not move to the next chunk until the current chunk's code has been explained clearly enough for manual review and approval.

## Track 1: Project foundation

### Step 1.1

Set up the FastAPI application package structure for a modular monolith.

Deliverables:

- application package layout
- app entrypoint
- module boundaries for auth, portal, ingestion, retrieval, audits, and ops

### Step 1.2

Add environment-driven settings management and baseline configuration models.

Deliverables:

- typed settings
- environment loading
- separation between app config and connector config

### Step 1.3

Add structured logging and request correlation foundations.

Deliverables:

- logger configuration
- request ID handling
- log format suitable for API and worker flows

### Step 1.4

Add health and readiness endpoints for the application shell.

Deliverables:

- liveness endpoint
- readiness endpoint
- dependency-aware readiness contract

## Track 2: Data and persistence foundation

### Step 2.1

Define core persistence models for users, sessions, sources, sync runs, documents, chunks, and audits.

Deliverables:

- schema model definitions
- department and source-type enums
- visibility and outcome code definitions

### Step 2.2

Define the normalized internal content model used between ingestion and indexing.

Deliverables:

- common content object
- parent trace model
- metadata contract for authority, freshness, and visibility

### Step 2.3

Add database initialization, migrations baseline, and pgvector-ready schema hooks.

Deliverables:

- database bootstrap
- migration baseline
- vector-capable chunk persistence design

### Step 2.4

Add repositories or persistence services for sessions, sources, sync runs, chunks, and audits.

Deliverables:

- create/read/update data access layer
- transaction boundaries
- retrieval-scope-aware query helpers

## Track 3: Identity and access

### Step 3.1

Implement JWT claim parsing and request auth-context construction.

Deliverables:

- token parsing boundary
- auth context model
- department and admin privilege extraction

### Step 3.2

Implement request dependency or middleware that attaches auth context to API requests.

Deliverables:

- protected request path support
- missing or invalid token handling
- request-scoped auth access

### Step 3.3

Implement authorization utilities for `department + shared` visibility scoping.

Deliverables:

- allowed visibility calculation
- admin access gating rules
- secure refusal helper contract

## Track 4: Employee portal base

### Step 4.1

Create the server-rendered employee portal shell.

Deliverables:

- main layout
- employee query view
- session list area
- answer and evidence placeholders

### Step 4.2

Implement employee session creation, listing, and resume behavior.

Deliverables:

- create session flow
- resume session flow
- saved per-user history

### Step 4.3

Implement employee question submission endpoint and UI binding.

Deliverables:

- request contract
- session-linked question submission
- synchronous placeholder response flow

## Track 5: Admin portal base

### Step 5.1

Create the admin portal shell and access guard.

Deliverables:

- admin layout
- protected admin route
- navigation for health, syncs, and audits

### Step 5.2

Implement connector health summary view.

Deliverables:

- connector status cards or table
- freshness summary by source and department
- failure count indicators

### Step 5.3

Implement sync run history view.

Deliverables:

- recent runs list
- status and timestamps
- processed item counts and error summary fields

## Track 6: Source registry and sync orchestration

### Step 6.1

Implement source registry models and admin CRUD foundations.

Deliverables:

- source registration records
- department ownership
- source-type-specific config placeholders

### Step 6.2

Implement sync run lifecycle tracking.

Deliverables:

- queued, running, success, failed, paused states
- timestamps
- summary metrics per run

### Step 6.3

Implement job dispatch contract for scheduled and manual sync triggers.

Deliverables:

- scheduled sync interface
- manual retry interface
- pause and resume control contract

## Track 7: PDF ingestion

### Step 7.1

Implement PDF source fetch and raw document registration flow.

Deliverables:

- source discovery or file registration
- raw document record creation
- sync bookkeeping

### Step 7.2

Implement PDF text extraction and section-aware normalization.

Deliverables:

- extracted text payload
- normalized document content
- source and parent trace metadata

### Step 7.3

Implement PDF chunk generation with trace-preserving metadata.

Deliverables:

- chunk objects
- section trace preservation
- authority and freshness propagation

## Track 8: GitHub ingestion

### Step 8.1

Implement GitHub source configuration and repository sync boundary.

Deliverables:

- repo identity config
- branch and path allowlist model
- sync entrypoint

### Step 8.2

Implement GitHub documentation and selected file normalization.

Deliverables:

- README and docs ingestion
- file metadata capture
- commit timestamp propagation

### Step 8.3

Implement GitHub chunk generation and index-ready output.

Deliverables:

- normalized chunks
- repo/file parent trace
- source-type-aware metadata

## Track 9: Slack ingestion

### Step 9.1

Implement Slack source configuration and channel sync boundary.

Deliverables:

- workspace and channel config model
- allowed channel mapping
- sync entrypoint

### Step 9.2

Implement Slack message and thread normalization.

Deliverables:

- channel metadata
- thread-aware normalized content
- timestamp and permalink trace fields

### Step 9.3

Implement Slack chunk generation for retrieval-ready content.

Deliverables:

- chunked thread units
- operational discussion metadata
- freshness propagation

## Track 10: Indexing and embeddings

### Step 10.1

Implement embedding provider abstraction and indexing service boundary.

Deliverables:

- embedding interface
- pluggable provider contract
- failure handling model

### Step 10.2

Implement chunk persistence with vector fields and retrieval metadata.

Deliverables:

- stored chunk records
- vector persistence path
- searchable metadata fields

### Step 10.3

Implement index update flow from normalized chunks to searchable records.

Deliverables:

- batch indexing path
- reindex or upsert handling
- sync-to-index traceability

## Track 11: Retrieval

### Step 11.1

Implement retrieval request contract with auth scope and session context.

Deliverables:

- retrieval input model
- allowed visibility input
- query metadata envelope

### Step 11.2

Implement scoped candidate retrieval over chunk data.

Deliverables:

- department and shared filtering
- vector similarity lookup baseline
- unauthorized result exclusion

### Step 11.3

Implement ranking layer for relevance, authority, freshness, and source type.

Deliverables:

- ranking input model
- weighted ranking baseline
- duplicate or overlap handling

### Step 11.4

Implement evidence package assembly for answer generation.

Deliverables:

- grouped citations
- parent-source trace bundle
- conflict-detection-ready evidence structure

## Track 12: Answer orchestration

### Step 12.1

Implement input validation for employee questions.

Deliverables:

- question validation rules
- refusal reason model
- unsafe prompt handling path

### Step 12.2

Implement conservative answer generation using retrieved evidence.

Deliverables:

- answer synthesis service
- citation attachment
- insufficient-evidence refusal path

### Step 12.3

Implement source conflict detection and dual-track answer output.

Deliverables:

- official-position section
- recent-operational section
- timestamps and conflict markers

### Step 12.4

Implement output validation for leakage and unsupported claims.

Deliverables:

- response validation path
- blocked output reasons
- final answer or refusal decision

## Track 13: Employee answer experience

### Step 13.1

Render answer output in the employee portal.

Deliverables:

- final answer section
- refusal section
- freshness signaling area

### Step 13.2

Render evidence tab with citations and source metadata.

Deliverables:

- citation list
- source-type labels
- timestamps
- trace links where allowed

### Step 13.3

Render dual-track conflict presentation in the employee experience.

Deliverables:

- official track view
- recent operational track view
- user-visible explanation of divergence

## Track 14: Admin operations and audits

### Step 14.1

Implement admin actions for retry, pause, and resume of sync jobs.

Deliverables:

- admin action endpoints
- state transition validation
- UI controls

### Step 14.2

Implement audit event recording across query and answer flow.

Deliverables:

- request audit events
- source consideration records
- answer or refusal outcome records

### Step 14.3

Implement audit viewer in the admin portal.

Deliverables:

- searchable audit list
- decision trace details
- admin-only enforcement

## Track 15: Freshness and staleness behavior

### Step 15.1

Implement freshness evaluation rules by source and connector.

Deliverables:

- freshness status computation
- stale threshold model
- connector-specific freshness summaries

### Step 15.2

Implement user-visible staleness signaling in answers when needed.

Deliverables:

- stale warning flags
- answer metadata indicators
- evidence freshness display

## Track 16: Validation and hardening

### Step 16.1

Implement test coverage for department-scoped retrieval guarantees.

### Step 16.2

Implement test coverage for refusal behavior and unauthorized-content protection.

### Step 16.3

Implement test coverage for dual-track conflict answers.

### Step 16.4

Implement test coverage for connector status, sync failures, and admin controls.

### Step 16.5

Implement test coverage for session persistence and evidence traceability.

## Track 17: Delivery readiness

### Step 17.1

Prepare local development bootstrap and environment documentation.

### Step 17.2

Prepare Dockerized app and dependency runtime setup.

### Step 17.3

Prepare operator-facing runbook draft for local deployment, sync operations, and failure triage.
