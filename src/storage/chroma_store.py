from typing import Any

from src.config.settings import get_settings
from src.models.schemas import CodeChunk, SearchResult

class ChromaChunkStore:
    def __init__(self) -> None:
        import chromadb
        from chromadb.config import Settings
        
        self.settings = get_settings()
        
        # We will use local persistent storage for Chroma in the workspace root
        db_path = str(self.settings.workspace_root / "chromadb")
        self.client = chromadb.PersistentClient(path=db_path)
        
        self.collection_name = self.settings.chroma_collection
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"}
        )

    def upsert_chunks(self, chunks: list[CodeChunk]) -> None:
        if not chunks:
            return
            
        ids = []
        embeddings = []
        documents = []
        metadatas = []
        
        for chunk in chunks:
            if not chunk.embedding:
                continue
            ids.append(chunk.id)
            embeddings.append(chunk.embedding)
            documents.append(chunk.raw_text)
            metadatas.append(chunk_payload(chunk))
            
        if ids:
            self.collection.upsert(
                ids=ids,
                embeddings=embeddings,
                documents=documents,
                metadatas=metadatas
            )

    def delete_chunks(self, chunk_ids: list[str]) -> None:
        if not chunk_ids:
            return
        self.collection.delete(ids=chunk_ids)

    def search(self, query_vector: list[float], repo_ids: set[str], limit: int) -> list[SearchResult]:
        try:
            where_clause = None
            if repo_ids:
                if len(repo_ids) == 1:
                    where_clause = {"repo_id": list(repo_ids)[0]}
                else:
                    where_clause = {"repo_id": {"$in": list(repo_ids)}}
                    
            results = self.collection.query(
                query_embeddings=[query_vector],
                n_results=limit,
                where=where_clause,
                include=["metadatas", "distances"]
            )
            
            if not results["metadatas"] or not results["metadatas"][0]:
                return []
                
            search_results = []
            for i in range(len(results["ids"][0])):
                metadata = results["metadatas"][0][i]
                distance = results["distances"][0][i] if results["distances"] else 0
                score = max(0.0, 1.0 - distance)
                search_results.append(payload_to_result(metadata, score))
                
            return search_results
        except Exception:
            return []

    def health(self) -> str:
        try:
            self.client.heartbeat()
            return "ok"
        except Exception as exc:
            return f"unavailable: {exc}"


def chunk_payload(chunk: CodeChunk) -> dict[str, Any]:
    return {
        "chunk_id": chunk.id,
        "repo_id": chunk.repo_id,
        "repo_name": chunk.repo_name,
        "source_web_url": chunk.source_web_url or "",
        "indexed_commit": chunk.indexed_commit or "",
        "file_path": chunk.file_path,
        "language": chunk.language,
        "symbol_name": chunk.symbol_name or "",
        "chunk_type": chunk.chunk_type,
        "start_line": chunk.start_line,
        "end_line": chunk.end_line,
        "ast_hash": chunk.ast_hash or "",
        "content_hash": chunk.content_hash,
        "summary": chunk.summary,
        "url": source_url_from_payload(chunk.source_web_url, chunk.indexed_commit, chunk.file_path, chunk.start_line, chunk.end_line) or "",
    }


def payload_to_result(payload: dict[str, Any], score: float) -> SearchResult:
    return SearchResult(
        chunk_id=str(payload.get("chunk_id", "")),
        repo_name=str(payload.get("repo_name", "")),
        file_path=str(payload.get("file_path", "")),
        start_line=int(payload.get("start_line", 1)),
        end_line=int(payload.get("end_line", 1)),
        score=score,
        source="dense",
        retrieval_sources=["dense", "chroma"],
        summary=str(payload.get("summary", "")),
        preview="",  # We might not have full raw text in metadata, but it's ok, UI will adapt
        url=payload.get("url") or None,
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
