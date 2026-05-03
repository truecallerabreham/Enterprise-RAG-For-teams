from src.graph.memory import MemoryGraph
from src.config.settings import get_settings
from src.models.schemas import CodeChunk, IngestionStatus, RepositoryCreate, RepositoryRecord


class AppState:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.repositories: dict[str, RepositoryRecord] = {}
        self.ingestions: dict[str, IngestionStatus] = {}
        self.chunks: dict[str, CodeChunk] = {}
        self.repo_chunks: dict[str, list[str]] = {}
        self.graph = MemoryGraph()
        self.vector_store_error: str | None = None
        self.vector_store = self._build_vector_store()

    def add_repository(self, payload: RepositoryCreate) -> RepositoryRecord:
        existing = self.find_repository_by_url(payload.git_url)
        if existing is not None:
            return existing
        repo = RepositoryRecord(**payload.model_dump())
        self.repositories[repo.id] = repo
        return repo

    def find_repository_by_url(self, git_url: str) -> RepositoryRecord | None:
        for repo in self.repositories.values():
            if repo.git_url == git_url:
                return repo
        return None

    def upsert_chunks(self, chunks: list[CodeChunk]) -> None:
        for chunk in chunks:
            self.chunks[chunk.id] = chunk
        if self.vector_store is not None:
            self.vector_store.upsert_chunks(chunks)

    def delete_chunks(self, chunk_ids: list[str]) -> None:
        if not chunk_ids:
            return
        for chunk_id in chunk_ids:
            self.chunks.pop(chunk_id, None)
        for repo_id, repo_chunk_ids in list(self.repo_chunks.items()):
            self.repo_chunks[repo_id] = [chunk_id for chunk_id in repo_chunk_ids if chunk_id not in chunk_ids]
        self.graph.remove_chunks(chunk_ids)
        if self.vector_store is not None:
            self.vector_store.delete_chunks(chunk_ids)

    def chunk_ids_for_files(self, repo_id: str, file_paths: set[str]) -> list[str]:
        return [
            chunk_id
            for chunk_id in self.repo_chunks.get(repo_id, [])
            if chunk_id in self.chunks and self.chunks[chunk_id].file_path in file_paths
        ]

    def vector_store_status(self) -> str:
        if self.vector_store is None:
            if self.settings.vector_store.lower() == "qdrant" and self.vector_store_error:
                return f"qdrant_unavailable: {self.vector_store_error}"
            return "memory"
        return self.vector_store.health()

    def _build_vector_store(self):
        if self.settings.vector_store.lower() != "qdrant":
            return None
        try:
            from src.storage.qdrant_store import QdrantChunkStore

            return QdrantChunkStore()
        except Exception as exc:
            self.vector_store_error = str(exc)
            return None


app_state = AppState()
