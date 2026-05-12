"""Comprehensive latency benchmark for Entreprise RAG project.

Measures execution time of all major pipeline components across multiple
storage backends: ChromaDB, Qdrant, MemoryGraph, and Neo4j.

Usage:
    python benchmarks/latency_test.py
"""

import json
import math
import os
import statistics
import tempfile
import time
import timeit
from pathlib import Path

from src.config.settings import get_settings, Settings
from src.graph.memory import MemoryGraph, normalize_symbol
from src.models.schemas import (
    ChunkCandidate,
    Citation,
    CodeChunk,
    DependencyEdge,
    RepositoryCreate,
    SearchResult,
    SymbolRecord,
)

# Override env to avoid accidental API calls during non-LLM benchmarks
os.environ.setdefault("VECTOR_STORE", "chroma")
os.environ.setdefault("LLM_PROVIDER", "groq")
os.environ.setdefault("GRAPH_PROVIDER", "memory")


BENCHMARK_ITERATIONS = 10
WARMUP_ITERATIONS = 2


def p95(data: list[float]) -> float:
    if not data:
        return 0.0
    sorted_data = sorted(data)
    index = int(math.ceil(0.95 * len(sorted_data))) - 1
    return sorted_data[max(0, index)]


def median(data: list[float]) -> float:
    return statistics.median(data) if data else 0.0


def fmt(seconds: float) -> str:
    if seconds < 0.001:
        return f"{seconds * 1_000_000:.1f} us"
    if seconds < 1.0:
        return f"{seconds * 1000:.2f} ms"
    return f"{seconds:.3f} s"


def stats(data: list[float]) -> dict:
    return {
        "min": round(min(data), 6),
        "max": round(max(data), 6),
        "avg": round(statistics.mean(data), 6),
        "median": round(median(data), 6),
        "p95": round(p95(data), 6),
    }


def print_stats(name: str, timings: list[float]) -> None:
    s = stats(timings)
    print(f"  {name:40s}  min={fmt(s['min']):>12s}  avg={fmt(s['avg']):>12s}  median={fmt(s['median']):>12s}  p95={fmt(s['p95']):>12s}")


# ─── Fixtures ────────────────────────────────────────────────────────────────

SAMPLE_PYTHON_CLASS = """
import os
import sys
from typing import Optional

class AuthenticationService:
    def __init__(self, api_key: str, timeout: int = 30):
        self.api_key = api_key
        self.timeout = timeout
        self._cache = {}

    def authenticate(self, user: str, password: str) -> bool:
        if user in self._cache:
            return self._cache[user]
        result = self._validate_credentials(user, password)
        self._cache[user] = result
        return result

    def _validate_credentials(self, user: str, password: str) -> bool:
        return len(user) > 0 and len(password) > 0

def default_config() -> dict:
    return {"timeout": 30, "retries": 3}
""".strip()

SAMPLE_JS_CODE = """
function calculateTotal(items) {
    let total = 0;
    for (const item of items) {
        total += item.price * item.quantity;
    }
    return applyDiscount(total);
}

function applyDiscount(amount) {
    if (amount > 100) {
        return amount * 0.9;
    }
    return amount;
}
""".strip()

SAMPLE_TS_CODE = """
interface User {
    id: string;
    name: string;
    email: string;
}

class UserRepository {
    private users: Map<string, User> = new Map();

    async findById(id: string): Promise<User | null> {
        return this.users.get(id) || null;
    }

    async save(user: User): Promise<void> {
        this.users.set(user.id, user);
    }
}
""".strip()

SAMPLE_MARKDOWN = """# Project Documentation

## Overview
This project implements a RAG system for code search.

## Components
- Ingestion pipeline: parses source code into chunks
- Storage layer: vector database + graph database
- Query pipeline: search, rerank, synthesize
""".strip()


def make_sample_files() -> Path:
    root = Path(tempfile.mkdtemp(prefix="bench_fixtures_"))
    (root / "auth.py").write_text(SAMPLE_PYTHON_CLASS)
    (root / "cart.js").write_text(SAMPLE_JS_CODE)
    (root / "repo.ts").write_text(SAMPLE_TS_CODE)
    (root / "readme.md").write_text(SAMPLE_MARKDOWN)
    return root


def make_chunk(repo_id: str, repo_name: str, symbol: str, text: str, start: int = 1, end: int = 5,
               embed_size: int = 1024) -> CodeChunk:
    import hashlib
    chunk_id = hashlib.sha256(f"{repo_id}:{symbol}:{start}".encode()).hexdigest()
    return CodeChunk(
        id=chunk_id,
        repo_id=repo_id,
        repo_name=repo_name,
        file_path=f"src/{symbol.lower().replace(' ', '_')}.py",
        language="python",
        symbol_name=symbol,
        chunk_type="function",
        start_line=start,
        end_line=end,
        raw_text=text,
        ast_hash=hashlib.sha256(text.encode()).hexdigest(),
        content_hash=hashlib.sha256(text.encode()).hexdigest(),
        summary=text.split("\n")[0] if text else "",
        embedding=[0.0] * embed_size,
        sparse_terms={},
    )


def make_search_result(chunk: CodeChunk, score: float, source: str = "dense") -> SearchResult:
    return SearchResult(
        chunk_id=chunk.id,
        repo_name=chunk.repo_name,
        file_path=chunk.file_path,
        start_line=chunk.start_line,
        end_line=chunk.end_line,
        score=score,
        source=source,
        retrieval_sources=[source],
        summary=chunk.summary,
        preview=chunk.raw_text[:500],
    )


# ─── Benchmark helpers ────────────────────────────────────────────────────────

def measure_latency(name: str, fn, iterations: int = BENCHMARK_ITERATIONS) -> dict:
    timings = []
    for _ in range(WARMUP_ITERATIONS):
        fn()
    for _ in range(iterations):
        start = time.perf_counter()
        fn()
        elapsed = time.perf_counter() - start
        timings.append(elapsed)
    result = stats(timings)
    print_stats(name, timings)
    return result


# ─── 1. Code Parsing ─────────────────────────────────────────────────────────

def bench_parsing():
    from src.ingestion.parser import CodeParser
    parser = CodeParser()

    def bench_python_ast():
        parser.parse_file(fixtures / "auth.py", fixtures)

    def bench_js_fallback():
        parser.parse_file(fixtures / "cart.js", fixtures)

    def bench_ts_fallback():
        parser.parse_file(fixtures / "repo.ts", fixtures)

    def bench_md_fallback():
        parser.parse_file(fixtures / "readme.md", fixtures)

    results = {}
    results["python_ast_parse"] = measure_latency("Python AST Parse", bench_python_ast)
    results["js_fallback_parse"] = measure_latency("JS Fallback Parse", bench_js_fallback)
    results["ts_fallback_parse"] = measure_latency("TS Fallback Parse", bench_ts_fallback)
    results["md_fallback_parse"] = measure_latency("Markdown Fallback Parse", bench_md_fallback)
    return results


# ─── 2. AST Hash Dedup ──────────────────────────────────────────────────────

def bench_hash_dedup():
    text = SAMPLE_PYTHON_CLASS * 10
    import hashlib

    def hash_text():
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    return {"ast_hash": measure_latency("AST Hash (SHA-256, dedup)", hash_text)}


# ─── 3. Embedding ────────────────────────────────────────────────────────────

def bench_embedding():
    from src.query.embedding import EmbeddingService
    embedder = EmbeddingService()
    texts = [
        "def authenticate_user(self, request): pass",
        "class DatabaseConnection: def connect(self): pass",
        "function calculateTotal(items) { return items.reduce((a,b) => a+b, 0); }",
    ]

    def embed_query():
        return embedder.embed_query("How does authentication work?")

    def embed_docs():
        return embedder.embed_documents(texts)

    results = {}
    results["embed_query"] = measure_latency("Embedding (query)", embed_query, iterations=5)
    results["embed_documents"] = measure_latency("Embedding (3 docs)", embed_docs, iterations=5)
    return results


# ─── 4. Vector Store Operations ──────────────────────────────────────────────

def bench_vector_stores():
    from src.storage.memory import AppState

    results = {}

    # ── ChromaDB ──
    try:
        settings = get_settings()
        original_store = settings.vector_store
        settings.vector_store = "chroma"
        chroma_state = AppState(persist=False)
        settings.vector_store = original_store

        # Populate with test chunks
        chunk = make_chunk("repo-1", "test-repo", "authenticate", "def authenticate(): pass\n" * 20,
                           embed_size=get_settings().vector_size)
        chunk.embedding = [0.1] * get_settings().vector_size  # non-zero embedding

        chroma_chunks = [chunk]

        def chroma_upsert():
            chroma_state.upsert_chunks(chroma_chunks)

        def chroma_search():
            chroma_state.vector_search([0.1] * get_settings().vector_size, set(), 10)

        results["chroma_upsert"] = measure_latency("ChromaDB Upsert (1 chunk)", chroma_upsert, iterations=5)
        results["chroma_search"] = measure_latency("ChromaDB Search (dense)", chroma_search, iterations=5)
    except Exception as exc:
        results["chroma_error"] = str(exc)

    # ── Qdrant ──
    try:
        settings = get_settings()
        original_store = settings.vector_store
        settings.vector_store = "qdrant"
        qdrant_state = AppState(persist=False)
        settings.vector_store = original_store

        chunk2 = make_chunk("repo-2", "test-qdrant", "search", "def search(): pass\n" * 20,
                            embed_size=get_settings().vector_size)
        chunk2.embedding = [0.2] * get_settings().vector_size

        qdrant_chunks = [chunk2]

        def qdrant_upsert():
            qdrant_state.upsert_chunks(qdrant_chunks)

        def qdrant_search():
            qdrant_state.vector_search([0.2] * get_settings().vector_size, set(), 10)

        results["qdrant_upsert"] = measure_latency("Qdrant Upsert (1 chunk)", qdrant_upsert, iterations=5)
        results["qdrant_search"] = measure_latency("Qdrant Search (dense)", qdrant_search, iterations=5)
    except Exception as exc:
        results["qdrant_error"] = str(exc)

    return results


# ─── 5. BM25 Sparse Search ──────────────────────────────────────────────────

def bench_sparse_search():
    from src.query.retrieval import sparse_search, sparse_terms
    from src.storage.memory import AppState

    state = AppState(persist=False)
    repo = state.add_repository(
        RepositoryCreate(name="bench-repo", git_url="https://github.com/bench/bench.git")
    )
    chunks = []
    for i in range(200):
        text = f"def function_{i}(param_{i}):\n    return param_{i} * {i}\n"
        c = make_chunk(repo.id, repo.name, f"function_{i}", text, start=1, end=3)
        c.sparse_terms = sparse_terms(f"function_{i} param_{i} {text}")
        chunks.append(c)
    state.upsert_chunks(chunks)

    def search():
        return sparse_search(state, "function param", {repo.id})

    return {"bm25_sparse_search": measure_latency("BM25 Sparse Search (200 chunks)", search)}


# ─── 6. RRF Fusion ──────────────────────────────────────────────────────────

def bench_rrf():
    from src.query.retrieval import reciprocal_rank_fusion
    chunks = [make_chunk("r", "rr", f"s{i}", f"text{i}", start=i, end=i+1) for i in range(50)]
    dense_set = [make_search_result(c, 1.0 - i * 0.01, "dense") for i, c in enumerate(chunks[:30])]
    sparse_set = [make_search_result(c, 1.0 - i * 0.02, "sparse") for i, c in enumerate(chunks[10:40])]

    def fusion():
        return reciprocal_rank_fusion([dense_set, sparse_set], limit=20)

    return {"rrf_fusion": measure_latency("RRF Fusion (50 results)", fusion)}


# ─── 7. Graph Operations ─────────────────────────────────────────────────────

def bench_graph_operations():
    results = {}

    # ── MemoryGraph ──
    mg = MemoryGraph()
    symbols = [SymbolRecord(chunk_id=f"c{i}", repo_id="r1", repo_name="r",
                            file_path=f"f{i}.py", symbol_name=f"sym{i}",
                            symbol_type="function", start_line=1, end_line=5)
               for i in range(100)]
    edges = [DependencyEdge(source_chunk_id=f"c{i}", target_symbol=f"sym{i+1}", relationship="references")
             for i in range(99)]
    mg.upsert_symbols(symbols)
    mg.upsert_edges(edges)

    def mg_related():
        return mg.related_chunk_ids("c0")

    def mg_snapshot():
        return mg.snapshot("r1")

    results["memorygraph_related"] = measure_latency("MemoryGraph related_chunk_ids", mg_related)
    results["memorygraph_snapshot"] = measure_latency("MemoryGraph snapshot (100 symbols)", mg_snapshot)

    # ── Neo4j ──
    try:
        s = get_settings()
        # Use Docker's configured password (docker-compose sets neo4j/password)
        neo4j_password = "password"
        from src.graph.neo4j_store import Neo4jGraphStore
        ng = Neo4jGraphStore(uri=s.neo4j_uri, user=s.neo4j_user, password=neo4j_password,
                             database=s.neo4j_database)
        ng.upsert_symbols(symbols)
        ng.upsert_edges(edges)

        def ng_related():
            return ng.related_chunk_ids("c0")

        def ng_snapshot():
            return ng.snapshot("r1")

        results["neo4j_related"] = measure_latency("Neo4j related_chunk_ids", ng_related)
        results["neo4j_snapshot"] = measure_latency("Neo4j snapshot (100 symbols)", ng_snapshot)
        ng.remove_chunks([f"c{i}" for i in range(100)])
        ng.close()
    except Exception as exc:
        results["neo4j_error"] = str(exc)

    return results


# ─── 8. Cross-Encoder Reranking ──────────────────────────────────────────────

def bench_reranker():
    from src.query.reranker import CrossEncoderReranker
    reranker = CrossEncoderReranker()
    chunks = [make_chunk("r", "r", f"f{i}", f"def f{i}(x): return x * {i}", start=1, end=2)
              for i in range(20)]
    results_list = [make_search_result(c, 0.5, "fused") for c in chunks]

    def rerank():
        return reranker.rerank("function implementation", results_list, 10)

    return {"cross_encoder_rerank": measure_latency("Cross-Encoder Rerank (20 candidates)", rerank, iterations=3)}


# ─── 9. Citation Validation ─────────────────────────────────────────────────

def bench_citations():
    from src.query.citations import validate_citations
    chunk = make_chunk("r", "r", "func", "def func(): pass\n" * 10, start=1, end=10)
    result = make_search_result(chunk, 0.9, "reranked")
    result.repo_name = "test-repo"
    result.start_line = 1
    result.end_line = 10

    valid_cites = [Citation(repo="test-repo", file=result.file_path, start_line=2, end_line=8)]
    invalid_cites = [Citation(repo="missing", file="missing.py", start_line=1, end_line=2)]

    def validate_valid():
        return validate_citations(valid_cites, [result])

    def validate_invalid():
        return validate_citations(invalid_cites, [result])

    results = {}
    results["citation_valid"] = measure_latency("Citation Validation (valid)", validate_valid)
    results["citation_invalid"] = measure_latency("Citation Validation (invalid)", validate_invalid)
    return results


# ─── 10. LLM Synthesis ──────────────────────────────────────────────────────

def bench_synthesis():
    from src.llm.synthesis import AnswerSynthesizer, extractive_fallback
    chunks = [make_chunk("r", "r", f"f{i}", f"def f{i}(): return {i}", start=1, end=2)
              for i in range(8)]
    results_list = [make_search_result(c, 0.5, "reranked") for c in chunks]

    # Extractive fallback (local, no API calls)
    def fallback():
        return extractive_fallback("How does authentication work?", results_list)

    results = {"extractive_fallback": measure_latency("Extractive Fallback Synthesis", fallback)}

    # Real Groq LLM
    try:
        synth = AnswerSynthesizer()
        results["groq_synthesis"] = measure_latency(
            "Groq LLM Synthesis (real API call)", lambda: synth.synthesize("How does authentication work in this codebase?", results_list),
            iterations=3
        )
    except Exception as exc:
        results["groq_synthesis_error"] = str(exc)

    return results


# ─── 11. Full Ingestion Pipeline ─────────────────────────────────────────────

def bench_full_ingestion():
    from src.ingestion.service import IngestionService
    from src.storage.memory import AppState

    state = AppState(persist=False)
    repo = state.add_repository(
        RepositoryCreate(name="bench-ingest", git_url="https://github.com/bench/ingest.git")
    )
    service = IngestionService(state)
    fixtures = make_sample_files()

    def ingest_all():
        service._ingest_path(repo, fixtures)

    return {"full_ingestion_e2e": measure_latency("Full Ingestion E2E (4 files)", ingest_all, iterations=3)}


# ─── 12. Full Query Pipeline ─────────────────────────────────────────────────

def bench_full_query():
    from src.query.service import QueryService
    from src.storage.memory import AppState

    state = AppState(persist=False)
    repo = state.add_repository(
        RepositoryCreate(name="bench-query", git_url="https://github.com/bench/query.git")
    )
    # Pre-populate with chunks
    fixtures = make_sample_files()
    from src.ingestion.service import IngestionService
    service = IngestionService(state)
    service._ingest_path(repo, fixtures)

    qs = QueryService(state)

    def query():
        return qs.answer(type("Q", (), {"question": "How does authentication work?", "repo_ids": [], "top_k": 10})())

    return {"full_query_e2e": measure_latency("Full Query E2E (4 chunks, real Groq)", query, iterations=3)}


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    global fixtures
    fixtures = make_sample_files()
    all_results = {}
    print("=" * 80)
    print("  Entreprise RAG — Latency Benchmarks")
    print(f"  Iterations per component: {BENCHMARK_ITERATIONS}")
    print("=" * 80)
    print()

    print("[1/12] Code Parsing")
    all_results["parsing"] = bench_parsing()
    print()

    print("[2/12] AST Hash Dedup")
    all_results["hashing"] = bench_hash_dedup()
    print()

    print("[3/12] Embedding")
    all_results["embedding"] = bench_embedding()
    print()

    print("[4/12] Vector Store Operations (ChromaDB vs Qdrant)")
    all_results["vector_stores"] = bench_vector_stores()
    print()

    print("[5/12] BM25 Sparse Search")
    all_results["sparse_search"] = bench_sparse_search()
    print()

    print("[6/12] RRF Fusion")
    all_results["rrf"] = bench_rrf()
    print()

    print("[7/12] Graph Operations (MemoryGraph vs Neo4j)")
    all_results["graph"] = bench_graph_operations()
    print()

    print("[8/12] Cross-Encoder Reranking")
    all_results["reranker"] = bench_reranker()
    print()

    print("[9/12] Citation Validation")
    all_results["citations"] = bench_citations()
    print()

    print("[10/12] LLM Synthesis")
    all_results["synthesis"] = bench_synthesis()
    print()

    print("[11/12] Full Ingestion Pipeline")
    all_results["full_ingestion"] = bench_full_ingestion()
    print()

    print("[12/12] Full Query Pipeline")
    all_results["full_query"] = bench_full_query()
    print()

    # Save results
    output_path = Path("benchmarks/latency_results.json")
    output_path.write_text(json.dumps(all_results, indent=2), encoding="utf-8")
    print(f"\nResults saved to {output_path}")


if __name__ == "__main__":
    main()
