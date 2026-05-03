# Implementation Plan: Cross-Repo Code Search RAG

## 1. Foundation

### 1.1 Project Structure

Create a backend package under `src/`:

```text
src/
  api/
  config/
  graph/
  ingestion/
  llm/
  models/
  query/
  storage/
  ui/
```

Use the existing Python project metadata in `pyproject.toml` and keep Python 3.11+ as the runtime target.

### 1.2 Configuration

Add environment-driven configuration for:

- Qdrant URL and collection names.
- Graph database provider and connection settings.
- Voyage API key and embedding model.
- LLM provider and model names.
- Managed repository workspace path.
- Optional development token or deploy-key location for private Git repositories.
- Ingestion limits and ignored path patterns.
- Reranker settings.

Do not add SSO, RBAC, user group, or authorization settings in this phase.

### 1.3 Core Models

Define Pydantic models for:

- Repository registration.
- Repository credentials reference.
- Indexing rules.
- Code chunks.
- Symbol records.
- Dependency edges.
- Ingestion jobs.
- Search results.
- Citations.
- Query requests and responses.
- Assistant activity events.

Chunk metadata must include:

- Repository ID and name.
- File path.
- Language.
- Symbol name when available.
- Chunk type.
- Start line.
- End line.
- AST hash.
- Content hash.
- Raw text.
- Summary.

## 2. Ingestion Pipeline

### 2.1 Repository Registration

Implement repository registration through `POST /repositories`.

The first version should use Git URL registration as the primary product flow.

The repository model should include:

- Repository name.
- Git URL.
- Default branch.
- Repository visibility: `public` or `private`.
- Optional credential reference for private repositories.
- Include and exclude indexing rules.

For public repositories, the backend should fetch directly from the Git URL.

For private repositories, the backend should support a development-friendly credential path using either:

- A personal access token provided through local configuration.
- A deploy key configured on the server.
- A request-time credential reference that points to a locally stored secret.

Do not build production secret management yet. Dedicated secret storage is future work.

Local repository paths may remain as a developer-only fallback for tests and debugging, but they should not be the primary user-facing flow.

### 2.2 Managed Git Workspace

Add a backend-managed workspace for repository clones and fetches.

The workspace should:

- Clone newly registered repositories into a deterministic server-side path.
- Fetch updates before each ingestion job.
- Checkout the configured branch or webhook commit.
- Keep enough Git history to compute diffs.
- Hide clone/fetch details from web UI and API users.
- Treat workspace files as cache that can be rebuilt from the registered Git URL.

### 2.3 Manual Ingestion

Implement `POST /repositories/{repo_id}/ingest`.

The endpoint should:

- Emit an assistant event requesting confirmation before ingestion.
- Create an ingestion job.
- Clone or fetch the repository in the managed workspace.
- Walk repository files.
- Apply include and exclude rules.
- Parse supported source files.
- Store chunk records, embeddings, summaries, and graph relationships.

### 2.4 Git Webhook Ingestion

Implement `POST /webhooks/git`.

The endpoint should:

- Accept push event metadata.
- Resolve the matching registered repository.
- Fetch the latest changes into the managed workspace.
- Compute changed files using `git diff`.
- Enqueue an incremental ingestion job.
- Process added, modified, deleted, and renamed files.

### 2.5 File Walker

Create an ingestion walker that:

- Skips ignored directories such as `.git`, `.venv`, `node_modules`, `dist`, `build`, and cache folders.
- Skips binary files.
- Detects language from extension.
- Tracks file status for full and incremental ingestion.
- Produces stable file metadata for downstream processing.

### 2.6 Tree-sitter Parser

Build `src/ingestion/parser.py`.

The parser should:

- Parse supported languages with Tree-sitter.
- Extract logical chunks for functions, classes, and methods.
- Capture symbol names and line ranges.
- Return structured chunk candidates.
- Fall back to text chunking when parsing fails.

Start with Python support, then add JavaScript/TypeScript after the parser interface is stable.

### 2.7 AST and Content Hashing

For every chunk:

- Compute an AST hash from the parsed structure when available.
- Compute a content hash from the raw chunk text.
- Skip summary, embedding, and storage updates when the AST hash is unchanged.
- Use the content hash as a fallback when AST hash is unavailable.

### 2.8 Chunk Enrichment

For changed chunks:

- Generate dense embeddings with Voyage.
- Generate sparse/BM25-ready text fields.
- Generate a short LLM summary.
- Extract imports, calls, definitions, and symbol references where practical.

## 3. Storage and Indexing

### 3.1 Qdrant Storage

Use Qdrant to store:

- Dense vectors.
- Sparse retrieval fields or payloads needed for sparse indexing.
- Raw code text.
- Chunk metadata.
- AI summaries.

Use deterministic chunk IDs based on repository ID, file path, symbol name, start line, and hash inputs.

### 3.2 Sparse Search

Add sparse keyword/BM25 support for:

- Exact function names.
- Class names.
- Constants.
- Variables.
- File paths.
- Import paths.

If Qdrant sparse search is not enough for the desired behavior, add a dedicated Tantivy-based index behind a storage interface.

### 3.3 Graph Storage

Use Neo4j or Kuzu for:

- Repository nodes.
- File nodes.
- Symbol nodes.
- Chunk nodes.
- Imports.
- Calls.
- Defines relationships.
- Depends-on relationships.

Graph writes should be idempotent so re-ingestion can safely update existing relationships.

### 3.4 Deleted Files and Chunks

When files are deleted:

- Remove or tombstone matching Qdrant chunks.
- Remove or deactivate matching graph nodes and edges.
- Record the deletion in the ingestion job result.

## 4. Query Pipeline

### 4.1 LangGraph Flow

Implement the query pipeline as LangGraph nodes:

1. Receive query.
2. Emit assistant planning event.
3. Run dense retrieval.
4. Run sparse retrieval.
5. Merge results with Reciprocal Rank Fusion.
6. Expand through graph relationships.
7. Rerank candidates.
8. Generate answer.
9. Validate citations.
10. Retry correction if needed.
11. Return final answer.

### 4.2 Dense and Sparse Retrieval

Dense retrieval should use embeddings for semantic intent.

Sparse retrieval should prioritize exact names, paths, constants, symbols, and identifiers.

Both retrieval paths should return a common `SearchResult` model.

### 4.3 Reciprocal Rank Fusion

Implement RRF to combine dense and sparse rankings.

The output should preserve:

- Source retrieval type.
- Original rank.
- Fused score.
- Chunk metadata.

### 4.4 Graph Expansion

Use the graph database to expand top results by:

- Imported symbols.
- Called functions.
- Defined classes.
- Related files.
- Cross-repo dependencies.

Graph-expanded chunks should be marked separately from directly retrieved chunks.

### 4.5 Reranking

Rerank the top candidates with a cross-encoder scoring interface.

The first implementation may use a simple local scoring stub while preserving the production interface for ONNX/TensorRT or another cross-encoder runtime.

### 4.6 Synthesis

Generate a final structured answer with:

- Direct answer.
- Explanation grounded in retrieved chunks.
- Citations containing repo, file, start line, and end line.
- Optional follow-up suggestions based on retrieved context.

### 4.7 Citation Validation

Validate that every citation:

- References a retrieved chunk.
- Uses a file path present in the retrieved context.
- Uses a line range covered by the retrieved context.

If validation fails, call a correction node with only the available retrieved context. Retry at most 2 times. If citations still fail, return an error response with assistant events explaining the failure.

## 5. Web UI and API

### 5.1 API Endpoints

Implement:

- `POST /repositories`
- `POST /repositories/{repo_id}/ingest`
- `POST /webhooks/git`
- `POST /query`
- `GET /ingestions/{job_id}`
- `GET /health`

### 5.2 Web UI

Build an internal web UI that supports:

- Repository registration by Git URL.
- Private repository credential selection for development/testing.
- Manual ingestion trigger with confirmation.
- Query input.
- Assistant activity timeline.
- Answer display.
- Citation display.
- Retrieved chunk inspection.
- Ingestion job status view.

### 5.3 Assistant Events

Emit structured events for:

- `needs_permission`
- `planning`
- `ingesting`
- `parsing`
- `embedding`
- `indexing`
- `searching`
- `expanding_graph`
- `reranking`
- `synthesizing`
- `validating_citations`
- `completed`
- `failed`

## 6. Testing Plan

### 6.1 Unit Tests

Add tests for:

- Tree-sitter chunk extraction by function, class, and method.
- Text fallback chunking for unsupported files.
- AST hash behavior.
- Deterministic chunk ID generation.
- Include and exclude path rules.
- RRF merge behavior.
- Citation validation.
- Assistant event creation.

### 6.2 Integration Tests

Add tests for:

- Full repository ingestion.
- Incremental ingestion for added, changed, deleted, and renamed files.
- Qdrant payload writes.
- Graph relationship writes.
- Dense and sparse retrieval returning common result models.
- Graph expansion adding related chunks.
- Query pipeline producing cited answers.
- Correction loop stopping after 2 retries.

### 6.3 API Tests

Add tests for:

- Repository registration success and validation errors.
- Public Git URL registration.
- Private Git URL registration with a credential reference.
- Manual ingestion job creation.
- Webhook ingestion request handling.
- Query response structure.
- Ingestion status response.
- Health endpoint response.

### 6.4 UI Tests

Add tests or browser checks for:

- Repository registration form.
- Ingestion confirmation flow.
- Query submission.
- Assistant activity timeline.
- Citation and retrieved chunk display.
- Error states for failed ingestion and failed citation validation.

## 7. Delivery Phases

### Phase 1: Backend Skeleton

- Create `src/` package layout.
- Add FastAPI app.
- Add config models.
- Add core Pydantic models.
- Add health endpoint.

### Phase 2: Ingestion

- Implement Git URL repository registration.
- Implement backend-managed clone/fetch workspace.
- Implement file walking.
- Implement Tree-sitter parser with text fallback.
- Implement hashing and deterministic chunk IDs.
- Add manual ingestion jobs.

### Phase 3: Storage

- Add Qdrant storage interface.
- Add embedding generation.
- Add summary generation.
- Add graph storage interface.
- Add deletion/tombstone behavior.

### Phase 4: Retrieval

- Add dense retrieval.
- Add sparse retrieval.
- Add RRF.
- Add graph expansion.
- Add reranking interface.

### Phase 5: Answering

- Add LangGraph orchestration.
- Add synthesis node.
- Add citation validation.
- Add correction loop.
- Add structured query API response.

### Phase 6: Web UI

- Add internal query UI.
- Add repository and ingestion UI.
- Add assistant event timeline.
- Add citation and retrieved chunk inspection.

### Phase 7: Hardening

- Add full test coverage described above.
- Add Docker Compose for dependencies.
- Add setup instructions to `README.md`.
- Add developer docs for running ingestion and queries locally.

## 8. Explicitly Deferred Security Work

Security is intentionally out of scope for the current build.

Do not implement:

- SSO token validation.
- RBAC filters.
- User group lookup.
- Authorization services.
- Qdrant metadata access-control filtering.
- Enterprise audit trails.

These should be documented as future work in `prd.md` and revisited after the core learning project works end to end.
