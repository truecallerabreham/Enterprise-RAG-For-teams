from typing import Any
from uuid import NAMESPACE_URL, uuid5

from src.config.settings import get_settings
from src.models.schemas import CodeChunk


class QdrantChunkStore:
    def __init__(self) -> None:
        from qdrant_client import QdrantClient

        self.settings = get_settings()
        self.client = QdrantClient(url=self.settings.qdrant_url)
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
    }


def qdrant_point_id(chunk_id: str) -> str:
    return str(uuid5(NAMESPACE_URL, chunk_id))
