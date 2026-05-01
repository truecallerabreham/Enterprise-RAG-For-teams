Problem..

By 2026, most advanced coding AI agents include a codebase retrieval system.
Large context windows (like Anthropic’s Claude with a 1-million token context) help the model read more code at once, but they do not solve the problem of answering questions across many repositories.

A simple search method like cosine similarity on raw text chunks often gives bad results because:

Generated code can create many similar-looking chunks that confuse search.
Large repositories often contain duplicate code.
Some important functions or symbols are rarely imported, so they are hard to find.

Because of this, real systems use a hybrid search approach, which combines:

Dense vector search (semantic similarity)
BM25 keyword search

The code is first split into AST-aware chunks (chunks based on the structure of the code).
Then a re-ranking model selects the most relevant results.
These systems also maintain a graph of symbol references (how functions, classes, and files depend on each other).

You only really understand these problems when you index a large, real-world codebase, not a small tutorial project.
When doing this, you measure performance using metrics like:

MRR@10 (how often the correct answer appears in the top results)
Citation faithfulness (whether the retrieved code actually supports the answer)
Incremental freshness (how quickly the index updates when code changes)

The hardest problems are infrastructure problems, for example:

A monorepo with 100,000 files
A commit that modifies half the repository
A question that requires information from multiple repositories to answer correctly.
Clearer Version

The system starts with an AST-aware ingestion pipeline.
Each file in the codebase is parsed using Tree-sitter to understand the structure of the code.

Instead of splitting code into chunks by a fixed number of tokens, the system splits it at logical boundaries, such as:

functions
classes
methods

Each chunk is then stored with three different representations:

Dense embedding
A semantic vector created using models like Voyage-code-3 or nomic-embed-code.
This helps the system find code that is semantically similar to a query.
Sparse keyword representation (BM25)
Traditional keyword search using BM25 so exact words in the query can match the code.
Short natural-language summary
A small description explaining what the code does.

The summary creates a third way to retrieve information.
For example:

A user asks: “How is X authorized?”
The code might contain check_permission
The summary mentions authorization, which allows the system to find it even though the word authorization is not in the code.
Retrieval Process

When a user asks a question, the system performs hybrid retrieval.

The query runs through:
Dense vector search
BM25 keyword search
The top results from both searches are merged together.
These results are sent to a re-ranking model that decides which chunks are most relevant.
Examples include:
Cohere Rerank-3
bge-reranker-v2-gemma-2b
The best-ranked chunks are then sent to a long-context language model that generates the final answer. Examples include:
Claude Sonnet 4.7
Llama 3.3 70B

The model is instructed to cite evidence for every claim, including:

file name
line numbers

If the generated answer does not include citations, it is rejected by a post-processing filter.

Keeping the Index Up to Date

One of the hardest challenges is keeping the system updated when the code changes.

When a developer pushes new code to Git:

The system checks the diff to see which files changed.
It determines which functions, classes, or symbols were modified.
Only the affected chunks are re-embedded.
Any cross-file relationships (such as imports or method calls) are recomputed.

This incremental process keeps the index accurate without reprocessing millions of lines of code after every commit

Aricheture 
git push --> webhook --> ingest worker (LlamaIndex Workflow)
                           |
                           v
             tree-sitter parse + AST chunk
                           |
            +--------------+----------------+
            v              v                v
          dense        BM25 index       summary (LLM)
        (Voyage / bge)  (Tantivy)        (Haiku 4.5)
            |              |                |
            +------> Qdrant / pgvector <----+
                            |
                            v
                      symbol graph (Neo4j / kuzu)
                            |
  query --> LangGraph agent (retrieve -> rerank -> synth)
                            |
                            v
                 Claude Sonnet 4.7 1M context / Gemini 2.0 Flash / Qwen3
                            |
                            v
                 answer + file:line citations

Stack
Parsing: tree-sitter with 17 language grammars (Python, TS, Rust, Go, Java, C++, etc.)
Dense embeddings: Voyage-code-3 (hosted) or nomic-embed-code-v1.5 (self-host), bge-code-v1 fallback
Sparse index: Tantivy (Rust) with BM25F, field-weighted on symbol name vs body
Vector DB: Qdrant 1.12 with hybrid search, or pgvector + pgvectorscale for teams under 50M vectors
Chunk summary model: Claude Haiku 4.5 or Gemini 2.5 Flash, prompt-cached
Re-ranker: Cohere rerank-3 or bge-reranker-v2-gemma-2b self-hosted
Orchestration: LlamaIndex Workflows for ingestion, LangGraph for query agent
Synthesizer: Claude Sonnet 4.7 (1M context) /gemini with prompt caching
Symbol graph: Neo4j (managed) or kuzu (embedded) for import and call edges
Observability:langsmith spans per retrieval + synthesis step

building plan 
Ingestion walker. Iterate git history on every push hook. Collect changed files. For each file, parse with tree-sitter, extract function and class nodes with their full source span. Emit chunk records {repo, path, start_line, end_line, symbol, body}.
Chunk summarizer. Batch chunks into Haiku 4.5 calls //other llms with prompt caching on the system preamble. Prompt: "Summarize this function in one sentence, naming its public contract and side effects." Store summary alongside the chunk.
Embedding pool. Two parallel queues: dense (Voyage-code-3 batch 128) and summary (same model, but on the summary string). Write vectors to Qdrant with payload {repo, path, start_line, end_line, symbol, kind}.
BM25 index. Field-weighted Tantivy index: symbol name weight 4, symbol body weight 1, summary weight 2. Enables "find the function named X" queries alongside "find the function that does X".
Symbol graph. For each chunk, record edges: imports (this file uses symbol Y from repo Z), calls (this function calls method M on class C), inheritance. Store in kuzu. Used at query time to expand retrieval across repo boundaries.
Query agent. LangGraph with three nodes. retrieve fires dense + BM25 in parallel, deduplicates by (repo, path, symbol). rerank runs the cross-encoder on top-50 and keeps top-10. synth calls Claude Sonnet 4.7 with the reranked chunks in context, caches the system prompt, requires file:line citations.
Citation enforcement. Parse the model output; any claim without a (repo/path:start-end) anchor gets flagged for re-ask or dropped. Return cited-only answer to the user.
Incremental re-index. On each webhook, compute the symbol-level diff. Only re-embed chunks whose text changed. Recompute symbol edges for chunks whose imports changed. Measure: a 50-file push re-indexed in under 60 seconds for a 2M-LOC fleet.
Eval. Label 100 cross-repo questions with gold file:line answers. Measure MRR@10, nDCG@10, citation faithfulness (fraction of claims with verifiable anchors), and p50/p99 latency.

## Architecture Refinements & Enterprise Best Practices

Based on production RAG patterns, the following design decisions are standardized for this architecture:

1. **Global Symbol Resolution**: We will use a **Heuristic-based Inverted Index**. When Repo A imports a symbol from Repo B, we map the import path to an inverted index of exported symbols across the fleet. If ambiguous, we prioritize based on the repository dependency graph (e.g., Repo A's `package.json` or `requirements.txt`).
2. **Hybrid Search Fusion**: We will rely on **Qdrant's native Reciprocal Rank Fusion (RRF)**. RRF normalizes the arbitrary score scales of Dense vectors and BM25 natively, avoiding fragile static alpha weighting.
3. **Handling Stale Summaries**: We will hash the AST node of each chunk (excluding whitespace/comments where possible). During an incremental sync, if the AST hash changes, we re-trigger the Haiku 4.5 summarizer. This prevents "semantic drift" where summaries become disconnected from the underlying logic.
4. **Citation "Re-asking" Loop**: The `synth` node will enforce **Structured JSON Output** for citations. If a citation fails the validation check (i.e., the cited repo/path doesn't exist in the retrieved context), LangGraph will loop back to an "Error Correction" node, injecting the error message and asking the model to fix the citation. Max 2 retries before graceful fallback.
5. **Multi-Repo RBAC**: Access control happens at the **Vector DB level**. Every chunk gets an `allowed_groups` metadata array. Qdrant will apply a strict "Must" metadata filter based on the querying user's Active Directory/SSO groups before any dense or sparse math is computed.
6. **Reranker Throughput**: To meet p99 latency goals, the Cross-Encoder will be optimized with **ONNX/TensorRT**. We will also introduce an adaptive threshold: rerank the top-30 by default, and only expand to 50 if the confidence scores of the top 30 are universally low.
7. **Evaluation Hard Negatives**: The eval dataset will include "adversarial" queries (e.g., asking for features that were explicitly deprecated or removed) to ensure the reranker effectively punishes irrelevant context and the LLM correctly states "I don't know" rather than hallucinating.
