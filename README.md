# Enterprise RAG for Teams

A production-grade, modular RAG system designed for internal departmental knowledge management and cross-repo code understanding.

## System Architecture

```mermaid
graph TD
    U[User Query] --> Auth[Auth Service Get SSO Groups]

    subgraph "Ingestion Pipeline"
        direction TB
        Hook[Git Push Webhook] --> Walker[Ingestion Walker]
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
        Auth --> Retrieve[Retrieve Node]
        
        Retrieve -->|Apply RBAC Filters| Qdrant
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

*(Instructions for setup will be added here as we build the components)*
