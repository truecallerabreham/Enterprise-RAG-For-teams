import math
import re
from collections import Counter, defaultdict

from src.models.schemas import CodeChunk, SearchResult
from src.storage.memory import AppState

VECTOR_SIZE = 64
RRF_K = 60


def tokenize(text: str) -> list[str]:
    return [token for token in re.findall(r"[A-Za-z_][A-Za-z0-9_]+", text.lower()) if len(token) > 2]


def sparse_terms(text: str) -> dict[str, int]:
    return dict(Counter(tokenize(text)))


def embed_text(text: str) -> list[float]:
    vector = [0.0] * VECTOR_SIZE
    for token in tokenize(text):
        index = stable_index(token)
        vector[index] += 1.0
    return normalize(vector)


def stable_index(token: str) -> int:
    value = 0
    for char in token:
        value = (value * 31 + ord(char)) % VECTOR_SIZE
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


def dense_search(state: AppState, question: str, repo_ids: set[str]) -> list[SearchResult]:
    query_vector = embed_text(question)
    results: list[SearchResult] = []
    for chunk in filtered_chunks(state, repo_ids):
        score = cosine(query_vector, chunk.embedding)
        if score > 0:
            results.append(to_result(chunk, score, "dense"))
    return sorted(results, key=lambda result: result.score, reverse=True)


def sparse_search(state: AppState, question: str, repo_ids: set[str]) -> list[SearchResult]:
    terms = tokenize(question)
    results: list[SearchResult] = []
    for chunk in filtered_chunks(state, repo_ids):
        score = 0.0
        for term in terms:
            score += chunk.sparse_terms.get(term, 0)
            if chunk.symbol_name and term in chunk.symbol_name.lower():
                score += 3.0
            if term in chunk.file_path.lower():
                score += 2.0
        if score > 0:
            results.append(to_result(chunk, score, "sparse"))
    return sorted(results, key=lambda result: result.score, reverse=True)


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
    )
