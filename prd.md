# Product Requirements Document: Cross-Repo Code Search RAG

## 1. Overview

The Cross-Repo Code Search RAG system helps engineers ask natural-language questions across multiple code repositories and receive accurate, cited answers. The project keeps the core enterprise retrieval architecture from `architecture.md`, but removes security, SSO, RBAC, authorization filters, and enterprise access controls from the current build to keep the learning curve manageable.

The current version focuses on code understanding, ingestion, retrieval quality, graph expansion, reranking, answer synthesis, citation validation, and a simple internal user experience.

## 2. Problem

Large engineering systems are spread across many repositories. Developers often need to understand how code works across repo boundaries, where behavior is implemented, which services depend on each other, and what file or function should be changed.

Traditional keyword search is useful for exact names, but it struggles with intent-based questions. Pure semantic search can find related code, but it can miss exact symbols, constants, or identifiers. A production-quality code assistant needs both, plus graph context and citation validation.

## 3. Goals

- Let users ask natural-language questions about one or more repositories.
- Return answers grounded in retrieved source code.
- Cite repository, file, and line ranges for every important claim.
- Support both semantic and exact-match retrieval.
- Understand code structure through Tree-sitter chunks.
- Support cross-repo dependency discovery through a symbol graph.
- Reduce hallucinated citations through validation and retry correction.
- Provide an internal web UI and API for learning, testing, and iteration.

## 4. Non-Goals for Current Build

- No SSO integration.
- No RBAC implementation.
- No authorization filtering.
- No user group resolution.
- No enterprise access-control enforcement.
- No production multi-tenant security model.

These are future-work items only.

## 5. Target Users

- Engineers trying to understand unfamiliar code.
- Tech leads tracing cross-repo behavior.
- New team members onboarding into a large codebase.
- Platform builders learning how enterprise RAG systems are assembled.
- Internal tool developers experimenting with retrieval architecture.

## 6. Core User Stories

- As an engineer, I can register multiple repositories so the system can search across them.
- As an engineer, I can register a repository by Git URL without cloning it on my own machine.
- As an engineer, I can provide a token or deploy key for private repositories during development/testing.
- As an engineer, I can trigger ingestion manually while I am learning and testing the system.
- As a developer workflow owner, I can later connect Git webhooks for incremental ingestion.
- As a user, I can ask a question in plain English and get an answer with citations.
- As a user, I can inspect retrieved chunks to understand why the answer was generated.
- As a user, I can see assistant activity messages that explain what the system is doing.
- As a user, I can approve major actions such as repository ingestion or broad searches.
- As a builder, I can observe ingestion status, retrieval stages, and citation validation behavior.

## 7. Product Scope

### Repository Ingestion

- Register repositories with name, Git URL, branch, and indexing rules.
- For public repositories, the backend fetches directly from the Git URL.
- For private repositories, the user provides a token or deploy key for backend fetch access.
- The backend performs clone, fetch, cache, and diff operations in a managed server-side workspace.
- Users do not need to clone repositories locally to use the web UI or API.
- Local path ingestion is a developer-only fallback for testing the ingestion pipeline.
- Support manual ingestion first.
- Add Git webhook ingestion for push events.
- Use `git diff` for incremental ingestion when prior state exists.
- Detect added, changed, deleted, and renamed files.
- Skip ignored paths such as virtual environments, dependency folders, build outputs, and binary files.

### Code Parsing and Chunking

- Use Tree-sitter to parse supported languages.
- Chunk code at logical boundaries such as functions, classes, and methods.
- Capture metadata for repo, file path, language, symbol name, start line, end line, and chunk hash.
- Fall back to text chunking when Tree-sitter parsing is unavailable or fails.
- Compute AST hashes so unchanged logic can skip expensive embedding and summary work.

### Chunk Representation

Each chunk should have three representations:

- Dense embedding for semantic search.
- Sparse keyword/BM25 representation for exact-symbol search.
- Short AI-generated summary describing the chunk's public contract or purpose.

### Storage

- Use Qdrant for dense vectors, sparse retrieval data, raw chunk text, metadata, and summaries.
- Use Neo4j or Kuzu for symbol and dependency relationships.
- Use deterministic chunk IDs so re-ingestion updates existing chunks instead of creating duplicates.
- Remove or tombstone chunks when source files are deleted.

### Query Pipeline

- Use LangGraph to orchestrate the query flow.
- Run dense and sparse retrieval.
- Merge rankings with Reciprocal Rank Fusion.
- Use the graph database to expand results through related symbols and dependencies.
- Rerank top candidates with a cross-encoder reranker.
- Generate a structured answer using an LLM.
- Require citations with repo, file, start line, and end line.
- Validate citations against retrieved context.
- Retry citation correction up to 2 times before returning a structured failure.

### Assistant UX

The assistant should behave like a vigilant intern:

- Announce high-level actions it is taking.
- Explain when it is ingesting, searching, reranking, validating citations, or asking for confirmation.
- Ask permission before major actions such as ingesting repositories, starting broad searches, or reprocessing large codebases.
- Show useful operational summaries without exposing private chain-of-thought.

### Web UI and API

- Provide an internal web UI for querying and inspecting results.
- Show assistant activity events.
- Show retrieved chunks and citations.
- Provide API endpoints for repository registration, ingestion, webhook ingestion, querying, ingestion status, and health checks.

## 8. Public API Requirements

### `POST /repositories`

Registers repository metadata, Git URL, default branch, optional private-repo credential reference, and indexing rules.

### `POST /repositories/{repo_id}/ingest`

Triggers manual ingestion after user confirmation.

### `POST /webhooks/git`

Receives Git push events and enqueues incremental ingestion.

### `POST /query`

Runs cross-repo retrieval and answer generation.

Expected response shape:

```json
{
  "answer": "string",
  "citations": [],
  "assistant_events": [],
  "retrieved_chunks": []
}
```

### `GET /ingestions/{job_id}`

Returns ingestion job status and errors.

### `GET /health`

Returns service readiness.

## 9. Success Criteria

- The system can ingest at least two repositories.
- Repositories can be registered by Git URL without requiring local user clones.
- Public repositories can be fetched by the backend directly.
- Private repositories can be fetched by the backend using a token or deploy key in the development setup.
- The system can answer natural-language questions using retrieved code context.
- Answers include repo, file, and line-range citations.
- Citation validation rejects citations that were not present in retrieved context.
- Dense and sparse retrieval both contribute to results.
- Graph expansion can add related cross-repo context.
- Incremental ingestion avoids unnecessary reprocessing of unchanged chunks.
- The web UI displays assistant activity, retrieved chunks, and citations clearly.

## 10. Future Work

- SSO authentication.
- RBAC and authorization filtering.
- User and group resolution.
- Metadata-level access control in Qdrant.
- Enterprise audit logging.
- Multi-tenant deployment hardening.
- Production observability and incident response workflows.
- GitHub App, GitLab App, or Bitbucket App integrations for production-grade repo access.
- Dedicated secret storage for private repository credentials.
