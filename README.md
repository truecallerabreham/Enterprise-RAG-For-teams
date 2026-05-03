# Entreprise RAG FOR DEV Team

A learning-oriented, modular RAG system for cross-repo code understanding. Users register repositories by Git URL, the backend manages clone/fetch work internally, and the API provides ingestion plus cited code-search answers.

## System Architecture

```mermaid
graph TD
    U[User Query] --> Retrieve[Retrieve Node]

    subgraph "Ingestion Pipeline"
        direction TB
        Register[Git URL Registration] --> Workspace[Managed Git Workspace]
        Hook[Git Push Webhook] --> Workspace
        Workspace --> Walker[Ingestion Walker]
        Walker --> TS[Tree-sitter Parser]
        TS --> Hash{AST Hash Changed?}
        Hash -->|No| Skip[Skip Save Compute]
        Hash -->|Yes| Extract[Extract Function and Metadata]
        
        Extract --> Sum[Claude Haiku Generate Summary]
        Extract --> Embed[Voyage Dense Embeddings]
        Extract --> Sparse[Tantivy BM25 Indexing]
        Extract --> Sym[Symbol Resolver Inverted Index]
    end

    subgraph "Storage Layer"
        direction TB
        Sum --> Qdrant[(Qdrant Vector DB)]
        Embed --> Qdrant
        Sparse --> Qdrant
        Sym --> Graph[(Neo4j Symbol Graph)]
    end

    subgraph "Query Pipeline"
        direction TB
        Retrieve --> Qdrant
        Qdrant -->|Reciprocal Rank Fusion| Merged[Merged Top Results]
        Retrieve --> Graph
        Graph -->|Cross Repo Expansion| Merged
        
        Merged --> Rerank[Cross Encoder Reranker]
        Rerank -->|Adaptive Threshold| Synth[Synth Node Claude Sonnet]
        
        Synth --> Verify{Citation Validation Loop}
        Verify -->|Invalid Citation| Error[Error Correction Node]
        Error --> Synth
    end

    Verify -->|Valid| Output[Final Verified Answer]
```

For a complete deep-dive text explanation of how these components work, see [architecture.md](./architecture.md).

## Getting Started

Run the API locally:

```powershell
python -m uvicorn src.api.main:app --reload --host 127.0.0.1 --port 8000
```

Health check:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

Open the internal web UI:

```text
http://127.0.0.1:8000/app
```

Run tests:

```powershell
python -m unittest discover -s tests
```

Start optional infrastructure:

```powershell
docker compose up -d qdrant neo4j
```

Use Qdrant for chunk vector persistence:

```powershell
$env:VECTOR_STORE="qdrant"
$env:QDRANT_URL="http://localhost:6333"
python -m uvicorn src.api.main:app --reload --host 127.0.0.1 --port 8000
```

If `VECTOR_STORE` is not set, the app uses in-memory storage so you can keep building without Docker.

Register a public Git repository:

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/repositories `
  -ContentType "application/json" `
  -Body '{"name":"fastapi","git_url":"https://github.com/fastapi/fastapi.git","default_branch":"master","visibility":"public"}'
```

Registration validates the Git remote and branch with `git ls-remote`. Placeholder URLs such as `https://github.com/example/demo-api.git` are rejected because they are not real reachable repositories. For private repositories, set the token in the server environment and put that environment variable name in the `credential_env_var` field.

Manual ingestion is permission-gated. First call with `confirm: false` to get the assistant permission event, then call with `confirm: true` when you want the backend to clone/fetch and index the repository.

Repository registration does not make a repository searchable by itself. A registered repository has only metadata until ingestion completes. In the UI, check the repository status and chunk count:

- `registered` or `needs_permission`: metadata exists, but there are no searchable chunks yet.
- `indexing`: the backend is cloning/fetching, parsing, and indexing.
- `indexed`: the repository has searchable chunks and graph symbols.
- `failed`: ingestion failed; the repository card shows the error.

Webhook ingestion uses the payload `before` and `after` commit SHAs to run `git diff --name-status`. Modified files are re-indexed, deleted files remove their old chunks, and renamed files clean up the previous path before indexing the new one.

Inspect the learned symbol graph for a repository:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/repositories/<repo_id>/graph
```

Current build note: SSO, RBAC, authorization filtering, and production secret storage are intentionally deferred while the core ingestion and retrieval system is built.
