import math
import re
from collections import Counter, defaultdict

from src.config.settings import get_settings
from src.models.schemas import CodeChunk, SearchResult
from src.storage.memory import AppState

RRF_K = 60


def tokenize(text: str) -> list[str]:
    return [token for token in re.findall(r"[A-Za-z_][A-Za-z0-9_]+", text.lower()) if len(token) > 2]


def sparse_terms(text: str) -> dict[str, int]:
    return dict(Counter(tokenize(text)))


def embed_text(text: str) -> list[float]:
    vector_size = get_settings().vector_size
    vector = [0.0] * vector_size
    for token in tokenize(text):
        index = stable_index(token, vector_size)
        vector[index] += 1.0
    return normalize(vector)


def stable_index(token: str, vector_size: int) -> int:
    value = 0
    for char in token:
        value = (value * 31 + ord(char)) % vector_size
    return value


def normalize(vector: list[float]) -> list[float]:
    magnitude = math.sqrt(sum(value * value for value in vector))
    if magnitude == 0:
        return vector
    return [value / magnitude for value in vector]


def cosine(left: list[float], right: list[float]) -> float:
    if not left or not right:
        return 0.0
    return sum(a * b for a, b in zip(left, right))


def dense_search(state: AppState, query_vector: list[float], repo_ids: set[str]) -> list[SearchResult]:
    if state.vector_store is not None:
        qdrant_results = state.vector_search(query_vector, repo_ids, limit=50)
        if qdrant_results:
            return qdrant_results
    results: list[SearchResult] = []
    for chunk in filtered_chunks(state, repo_ids):
        score = cosine(query_vector, chunk.embedding)
        if score > 0:
            results.append(to_result(chunk, score, "dense"))
    return sorted(results, key=lambda result: result.score, reverse=True)


def sparse_search(state: AppState, question: str, repo_ids: set[str]) -> list[SearchResult]:
    terms = tokenize(question)
    chunks = filtered_chunks(state, repo_ids)
    doc_count = max(len(chunks), 1)
    doc_freq: Counter[str] = Counter()
    doc_lengths: dict[str, int] = {}
    for chunk in chunks:
        doc_lengths[chunk.id] = sum(chunk.sparse_terms.values())
        for term in chunk.sparse_terms:
            doc_freq[term] += 1
    avg_doc_length = sum(doc_lengths.values()) / max(len(doc_lengths), 1)
    results: list[SearchResult] = []
    for chunk in chunks:
        score = 0.0
        for term in terms:
            score += bm25(term, chunk, doc_freq, doc_count, doc_lengths.get(chunk.id, 0), avg_doc_length)
            if chunk.symbol_name and term in chunk.symbol_name.lower():
                score += 3.0
            if term in chunk.file_path.lower():
                score += 2.0
        if score > 0:
            results.append(to_result(chunk, score, "sparse"))
    return sorted(results, key=lambda result: result.score, reverse=True)


def bm25(
    term: str,
    chunk: CodeChunk,
    doc_freq: Counter[str],
    doc_count: int,
    doc_length: int,
    avg_doc_length: float,
    k1: float = 1.5,
    b: float = 0.75,
) -> float:
    frequency = chunk.sparse_terms.get(term, 0)
    if frequency == 0:
        return 0.0
    idf = math.log(1 + (doc_count - doc_freq.get(term, 0) + 0.5) / (doc_freq.get(term, 0) + 0.5))
    denominator = frequency + k1 * (1 - b + b * doc_length / max(avg_doc_length, 1))
    return idf * (frequency * (k1 + 1)) / denominator


def reciprocal_rank_fusion(result_sets: list[list[SearchResult]], limit: int) -> list[SearchResult]:
    fused_scores: dict[str, float] = defaultdict(float)
    originals: dict[str, SearchResult] = {}
    sources: dict[str, set[str]] = defaultdict(set)

    for result_set in result_sets:
        for rank, result in enumerate(result_set, start=1):
            fused_scores[result.chunk_id] += 1.0 / (RRF_K + rank)
            originals.setdefault(result.chunk_id, result)
            sources[result.chunk_id].add(result.source)

    fused: list[SearchResult] = []
    for chunk_id, score in fused_scores.items():
        result = originals[chunk_id].model_copy(update={"score": score, "source": "fused"})
        result.retrieval_sources = sorted(sources[chunk_id])
        fused.append(result)
    return sorted(fused, key=lambda result: result.score, reverse=True)[:limit]


def graph_expand(state: AppState, results: list[SearchResult], repo_ids: set[str], limit: int) -> list[SearchResult]:
    existing = {result.chunk_id for result in results}
    expanded = list(results)
    for result in results[:limit]:
        for related_chunk_id in state.graph.related_chunk_ids(result.chunk_id):
            if related_chunk_id in existing:
                continue
            chunk = state.chunks.get(related_chunk_id)
            if chunk is None or (repo_ids and chunk.repo_id not in repo_ids):
                continue
            expanded.append(to_result(chunk, 0.01, "graph"))
            existing.add(chunk.id)
    return expanded


def rerank(question: str, results: list[SearchResult], limit: int) -> list[SearchResult]:
    question_terms = set(tokenize(question))
    reranked: list[SearchResult] = []
    for result in results:
        text_terms = set(tokenize(f"{result.file_path} {result.summary} {result.preview}"))
        overlap = len(question_terms & text_terms)
        score = result.score + overlap * 0.1
        reranked.append(result.model_copy(update={"score": score, "source": "reranked"}))
    return sorted(reranked, key=lambda result: result.score, reverse=True)[:limit]


def filtered_chunks(state: AppState, repo_ids: set[str]) -> list[CodeChunk]:
    return [chunk for chunk in state.chunks.values() if not repo_ids or chunk.repo_id in repo_ids]


def to_result(chunk: CodeChunk, score: float, source: str) -> SearchResult:
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
        url=source_url(chunk),
    )


def source_url(chunk: CodeChunk) -> str | None:
    if not chunk.source_web_url:
        return None
    ref = chunk.indexed_commit or "HEAD"
    path = chunk.file_path.replace("\\", "/")
    return f"{chunk.source_web_url}/blob/{ref}/{path}#L{chunk.start_line}-L{chunk.end_line}"
