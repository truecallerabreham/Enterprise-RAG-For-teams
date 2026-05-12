import json
from pathlib import Path
from threading import RLock

from src.graph.memory import MemoryGraph
from src.config.settings import get_settings
from src.ingestion.git_workspace import source_web_url
from src.models.schemas import CodeChunk, IngestionStatus, RepositoryCreate, RepositoryRecord


class AppState:
    def __init__(self, persist: bool = True) -> None:
        self.settings = get_settings()
        self.persist = persist
        self.lock = RLock()
        self.state_path = self.settings.workspace_root / "app_state.json"
        self.repositories: dict[str, RepositoryRecord] = {}
        self.ingestions: dict[str, IngestionStatus] = {}
        self.chunks: dict[str, CodeChunk] = {}
        self.repo_chunks: dict[str, list[str]] = {}
        self.graph_error: str | None = None
        self.graph = self._build_graph_store()
        self.vector_store_error: str | None = None
        self.vector_store = self._build_vector_store()
        if self.persist:
            self.load_state()

    def add_repository(self, payload: RepositoryCreate) -> RepositoryRecord:
        with self.lock:
            existing = self.find_repository_by_url(payload.git_url)
            if existing is not None:
                return existing
            repo = RepositoryRecord(**payload.model_dump())
            repo.source_web_url = source_web_url(repo.git_url)
            self.repositories[repo.id] = repo
            self.save_state()
            return repo

    def delete_repository(self, repo_id: str) -> bool:
        with self.lock:
            repo = self.repositories.pop(repo_id, None)
            if repo is None:
                return False
            self.delete_chunks(self.repo_chunks.get(repo_id, []))
            self.repo_chunks.pop(repo_id, None)
            self.ingestions = {
                job_id: job for job_id, job in self.ingestions.items() if job.repo_id != repo_id
            }
            self.save_state()
            return True

    def find_repository_by_url(self, git_url: str) -> RepositoryRecord | None:
        for repo in self.repositories.values():
            if repo.git_url == git_url:
                return repo
        return None

    def upsert_chunks(self, chunks: list[CodeChunk]) -> None:
        with self.lock:
            for chunk in chunks:
                self.chunks[chunk.id] = chunk
        if self.vector_store is not None:
            self.vector_store.upsert_chunks(chunks)
        for repo_id in {chunk.repo_id for chunk in chunks}:
            self.refresh_repository_counts(repo_id)

    def delete_chunks(self, chunk_ids: list[str]) -> None:
        with self.lock:
            if not chunk_ids:
                return
            for chunk_id in chunk_ids:
                self.chunks.pop(chunk_id, None)
            for repo_id, repo_chunk_ids in list(self.repo_chunks.items()):
                self.repo_chunks[repo_id] = [chunk_id for chunk_id in repo_chunk_ids if chunk_id not in chunk_ids]
            self.graph.remove_chunks(chunk_ids)
        if self.vector_store is not None:
            self.vector_store.delete_chunks(chunk_ids)
        for repo_id in list(self.repositories):
            self.refresh_repository_counts(repo_id)

    def chunk_ids_for_files(self, repo_id: str, file_paths: set[str]) -> list[str]:
        return [
            chunk_id
            for chunk_id in self.repo_chunks.get(repo_id, [])
            if chunk_id in self.chunks and self.chunks[chunk_id].file_path in file_paths
        ]

    def refresh_repository_counts(self, repo_id: str) -> None:
        repo = self.repositories.get(repo_id)
        if repo is None:
            return
        repo.chunk_count = len([chunk_id for chunk_id in self.repo_chunks.get(repo_id, []) if chunk_id in self.chunks])
        self.save_state()

    def save_ingestion(self, job: IngestionStatus) -> None:
        with self.lock:
            self.ingestions[job.id] = job
            self.save_state()

    def save_state(self) -> None:
        if not self.persist:
            return
        data = {
            "repositories": [repo.model_dump(mode="json") for repo in self.repositories.values()],
            "ingestions": [job.model_dump(mode="json") for job in self.ingestions.values()],
        }
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def load_state(self) -> None:
        if not self.state_path.exists():
            return
        data = json.loads(self.state_path.read_text(encoding="utf-8"))
        self.repositories = {
            repo.id: repo for repo in (RepositoryRecord.model_validate(item) for item in data.get("repositories", []))
        }
        for repo in self.repositories.values():
            if repo.source_web_url is None:
                repo.source_web_url = source_web_url(repo.git_url)
            repo.chunk_count = 0
            if repo.indexing_status in {"indexing", "indexed"}:
                repo.indexing_status = "registered"
                repo.last_error = "Server restarted; run ingestion again to rebuild the in-memory index."
        self.ingestions = {
            job.id: job for job in (IngestionStatus.model_validate(item) for item in data.get("ingestions", []))
        }

    def vector_store_status(self) -> str:
        if self.vector_store is None:
            if self.settings.vector_store.lower() == "qdrant" and self.vector_store_error:
                return f"qdrant_unavailable: {self.vector_store_error}"
            return "memory"
        return self.vector_store.health()

    def vector_search(self, query_vector: list[float], repo_ids: set[str], limit: int):
        if self.vector_store is None:
            return []
        return self.vector_store.search(query_vector, repo_ids, limit)

    def _build_vector_store(self):
        if self.settings.vector_store.lower() == "qdrant":
            try:
                from src.storage.qdrant_store import QdrantChunkStore
                return QdrantChunkStore()
            except Exception as exc:
                self.vector_store_error = str(exc)
                return None
        elif self.settings.vector_store.lower() == "chroma":
            try:
                from src.storage.chroma_store import ChromaChunkStore
                return ChromaChunkStore()
            except Exception as exc:
                self.vector_store_error = str(exc)
                return None
        return None

    def _build_graph_store(self):
        if self.settings.graph_provider.lower() == "neo4j":
            try:
                from src.graph.neo4j_store import Neo4jGraphStore
                return Neo4jGraphStore(
                    uri=self.settings.neo4j_uri,
                    user=self.settings.neo4j_user,
                    password=self.settings.neo4j_password,
                    database=self.settings.neo4j_database,
                )
            except Exception as exc:
                self.graph_error = str(exc)
                return MemoryGraph()
        return MemoryGraph()

    def graph_store_status(self) -> str:
        if isinstance(self.graph, MemoryGraph):
            if self.graph_error:
                return f"neo4j_unavailable: {self.graph_error}"
            return "memory"
        try:
            self.graph._verify_connectivity()
            return "ok"
        except Exception as exc:
            return f"unavailable: {exc}"


app_state = AppState()
