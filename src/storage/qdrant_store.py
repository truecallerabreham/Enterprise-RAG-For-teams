from typing import Any
from uuid import NAMESPACE_URL, uuid5

from src.config.settings import get_settings
from src.models.schemas import CodeChunk, SearchResult


class QdrantChunkStore:
    def __init__(self) -> None:
        import os
        from qdrant_client import QdrantClient

        self.settings = get_settings()
        api_key = os.getenv("QDRANT_API_KEY") or None
        self.client = QdrantClient(url=self.settings.qdrant_url, api_key=api_key)
        self.collection = self.settings.qdrant_collection
        self._ensure_collection()

    def upsert_chunks(self, chunks: list[CodeChunk]) -> None:
        if not chunks:
            return
        from qdrant_client.models import PointStruct

        points = [
            PointStruct(id=qdrant_point_id(chunk.id), vector=chunk.embedding, payload=chunk_payload(chunk))
            for chunk in chunks
            if chunk.embedding
        ]
        if points:
            self.client.upsert(collection_name=self.collection, points=points)

    def delete_chunks(self, chunk_ids: list[str]) -> None:
        if not chunk_ids:
            return
        self.client.delete(collection_name=self.collection, points_selector=[qdrant_point_id(chunk_id) for chunk_id in chunk_ids])

    def search(self, query_vector: list[float], repo_ids: set[str], limit: int) -> list[SearchResult]:
        try:
            from qdrant_client.models import FieldCondition, Filter, MatchAny

            query_filter = None
            if repo_ids:
                query_filter = Filter(
                    must=[FieldCondition(key="repo_id", match=MatchAny(any=list(repo_ids)))]
                )
            points = self.client.query_points(
                collection_name=self.collection,
                query=query_vector,
                query_filter=query_filter,
                limit=limit,
                with_payload=True,
            ).points
            return [payload_to_result(point.payload or {}, float(point.score)) for point in points]
        except Exception:
            return []

    def health(self) -> str:
        try:
            self.client.get_collection(self.collection)
            return "ok"
        except Exception as exc:
            return f"unavailable: {exc}"

    def _ensure_collection(self) -> None:
        from qdrant_client.models import Distance, VectorParams

        collections = self.client.get_collections().collections
        if any(collection.name == self.collection for collection in collections):
            return
        self.client.create_collection(
            collection_name=self.collection,
            vectors_config=VectorParams(size=self.settings.vector_size, distance=Distance.COSINE),
        )


def chunk_payload(chunk: CodeChunk) -> dict[str, Any]:
    return {
        "chunk_id": chunk.id,
        "repo_id": chunk.repo_id,
        "repo_name": chunk.repo_name,
        "source_web_url": chunk.source_web_url,
        "indexed_commit": chunk.indexed_commit,
        "file_path": chunk.file_path,
        "language": chunk.language,
        "symbol_name": chunk.symbol_name,
        "chunk_type": chunk.chunk_type,
        "start_line": chunk.start_line,
        "end_line": chunk.end_line,
        "ast_hash": chunk.ast_hash,
        "content_hash": chunk.content_hash,
        "raw_text": chunk.raw_text,
        "summary": chunk.summary,
        "sparse_terms": chunk.sparse_terms,
        "url": source_url_from_payload(chunk.source_web_url, chunk.indexed_commit, chunk.file_path, chunk.start_line, chunk.end_line),
    }


def qdrant_point_id(chunk_id: str) -> str:
    return str(uuid5(NAMESPACE_URL, chunk_id))


def payload_to_result(payload: dict[str, Any], score: float) -> SearchResult:
    return SearchResult(
        chunk_id=str(payload.get("chunk_id", "")),
        repo_name=str(payload.get("repo_name", "")),
        file_path=str(payload.get("file_path", "")),
        start_line=int(payload.get("start_line", 1)),
        end_line=int(payload.get("end_line", 1)),
        score=score,
        source="dense",
        retrieval_sources=["dense", "qdrant"],
        summary=str(payload.get("summary", "")),
        preview=str(payload.get("raw_text", ""))[:500],
        url=payload.get("url"),
    )


def source_url_from_payload(
    source_web_url: str | None,
    indexed_commit: str | None,
    file_path: str,
    start_line: int,
    end_line: int,
) -> str | None:
    if not source_web_url:
        return None
    ref = indexed_commit or "HEAD"
    normalized_path = file_path.replace("\\", "/")
    return f"{source_web_url}/blob/{ref}/{normalized_path}#L{start_line}-L{end_line}"
