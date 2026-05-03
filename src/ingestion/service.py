import hashlib
from threading import Thread
from pathlib import Path
from uuid import uuid4

from src.config.settings import get_settings
from src.ingestion.git_workspace import GitWorkspace
from src.ingestion.parser import CodeParser
from src.models.schemas import (
    AssistantEvent,
    CodeChunk,
    DependencyEdge,
    IngestionRequest,
    IngestionStatus,
    RepositoryRecord,
    SymbolRecord,
)
from src.query.embedding import EmbeddingService
from src.query.retrieval import sparse_terms
from src.storage.memory import AppState


IGNORED_DIRS = {".git", ".venv", "node_modules", "dist", "build", "__pycache__", ".pytest_cache", ".mypy_cache"}
SOURCE_SUFFIXES = {".py", ".js", ".jsx", ".ts", ".tsx", ".md", ".toml", ".yaml", ".yml", ".json"}


class IngestionService:
    def __init__(self, state: AppState) -> None:
        self.state = state
        self.workspace = GitWorkspace()
        self.parser = CodeParser()
        self.embedding = EmbeddingService()
        self.settings = get_settings()

    def ingest_repository(self, repo: RepositoryRecord, request: IngestionRequest) -> IngestionStatus:
        job = IngestionStatus(
            id=str(uuid4()),
            repo_id=repo.id,
            status="needs_permission" if not request.confirm else "running",
            current_step="waiting for permission" if not request.confirm else "queued",
            progress_percent=0 if not request.confirm else 5,
            assistant_events=[
                AssistantEvent(
                    type="needs_permission" if not request.confirm else "ingesting",
                    message=(
                        "Confirm ingestion before the backend clones/fetches and indexes this repository."
                        if not request.confirm
                        else "Preparing managed Git workspace and starting ingestion."
                    ),
                )
            ],
        )
        repo.last_ingestion_id = job.id
        if not request.confirm:
            repo.indexing_status = "needs_permission"
            self.state.save_ingestion(job)
            return job

        repo.indexing_status = "indexing"
        repo.last_error = None
        self.state.save_ingestion(job)
        Thread(target=self._run_ingestion_job, args=(repo.id, request, job.id), daemon=True).start()
        return job

    def _run_ingestion_job(self, repo_id: str, request: IngestionRequest, job_id: str) -> None:
        repo = self.state.repositories[repo_id]
        job = self.state.ingestions[job_id]
        try:
            self._update_job(job, "cloning/fetching", 15, "ingesting", "Cloning or fetching repository in managed workspace.")
            repo_path = self.workspace.prepare(repo)
            repo.indexed_commit = self.workspace.current_commit(repo_path)
            self.state.save_state()
            self._update_job(job, "diffing", 30, "ingesting", "Checking changed files for incremental ingestion.")
            changes = self.workspace.changed_file_statuses(repo_path, request.base_ref, request.webhook_commit)
            self._update_job(job, "parsing", 45, "parsing", "Parsing source files and extracting code chunks.")
            chunks = self._ingest_path(repo, repo_path, changes=changes or None)
            self._update_job(job, "indexing", 80, "indexing", "Writing chunks, symbols, and retrieval metadata.")
            job.status = "completed"
            job.current_step = "completed"
            job.progress_percent = 100
            job.files_seen = len({chunk.file_path for chunk in chunks})
            job.chunks_indexed = self.state.repositories[repo.id].chunk_count
            repo.indexing_status = "indexed"
            job.assistant_events.append(
                AssistantEvent(
                    type="completed",
                    message=f"Repository ingestion completed. Indexed {repo.chunk_count} searchable chunks.",
                )
            )
        except Exception as exc:
            job.status = "failed"
            job.current_step = "failed"
            job.progress_percent = 100
            job.errors.append(str(exc))
            repo.indexing_status = "failed"
            repo.last_error = str(exc)
            job.assistant_events.append(AssistantEvent(type="failed", message=f"Ingestion failed: {exc}"))
        self.state.save_ingestion(job)

    def _update_job(
        self,
        job: IngestionStatus,
        step: str,
        progress_percent: int,
        event_type: str,
        message: str,
    ) -> None:
        job.current_step = step
        job.progress_percent = progress_percent
        job.assistant_events.append(AssistantEvent(type=event_type, message=message))
        self.state.save_ingestion(job)
        return job

    def _ingest_path(self, repo: RepositoryRecord, repo_path: Path, changes: list | None = None) -> list[CodeChunk]:
        parsed_chunks: list[CodeChunk] = []
        source_files = self._source_files(repo_path, changes)
        if changes is None:
            self._prune_missing_files(repo, repo_path, source_files)
        else:
            self._remove_changed_or_deleted_chunks(repo, changes)

        for path in source_files:
            for candidate in self.parser.parse_file(path, repo_path):
                chunk_id = stable_chunk_id(repo.id, candidate.file_path, candidate.symbol_name, candidate.start_line)
                existing = self.state.chunks.get(chunk_id)
                hash_value = candidate.ast_hash or candidate.content_hash
                if existing and (existing.ast_hash or existing.content_hash) == hash_value:
                    parsed_chunks.append(existing)
                    continue
                chunk = CodeChunk(
                    id=chunk_id,
                    repo_id=repo.id,
                    repo_name=repo.name,
                    source_web_url=repo.source_web_url,
                    indexed_commit=repo.indexed_commit,
                    file_path=candidate.file_path,
                    language=candidate.language,
                    symbol_name=candidate.symbol_name,
                    chunk_type=candidate.chunk_type,
                    start_line=candidate.start_line,
                    end_line=candidate.end_line,
                    ast_hash=candidate.ast_hash,
                    content_hash=candidate.content_hash,
                    raw_text=candidate.raw_text,
                    summary=summarize_chunk(candidate.raw_text),
                    embedding=self.embedding.embed_document(
                        f"{candidate.file_path} {candidate.symbol_name or ''} {candidate.raw_text}"
                    ),
                    sparse_terms=sparse_terms(
                        f"{candidate.file_path} {candidate.symbol_name or ''} {candidate.raw_text}"
                    ),
                )
                self.state.upsert_chunks([chunk])
                parsed_chunks.append(chunk)
                self.state.graph.upsert_symbols([symbol_from_chunk(chunk)])
                self.state.graph.upsert_edges(extract_dependency_edges(chunk, candidate.dependencies))
        previous = [chunk_id for chunk_id in self.state.repo_chunks.get(repo.id, []) if chunk_id in self.state.chunks]
        merged = list(dict.fromkeys(previous + [chunk.id for chunk in parsed_chunks]))
        self.state.repo_chunks[repo.id] = merged
        self.state.refresh_repository_counts(repo.id)
        return parsed_chunks

    def _source_files(self, repo_path: Path, changes: list | None = None) -> list[Path]:
        if changes is not None:
            files: list[Path] = []
            for change in changes:
                if change.status == "D":
                    continue
                path = repo_path / change.path
                if self._is_source_file(repo_path, path):
                    files.append(path)
            return sorted(files)
        files: list[Path] = []
        for path in repo_path.rglob("*"):
            if self._is_source_file(repo_path, path):
                files.append(path)
        return sorted(files)

    def _is_source_file(self, repo_path: Path, path: Path) -> bool:
        if not path.exists() or not path.is_file():
            return False
        if any(part in IGNORED_DIRS for part in path.relative_to(repo_path).parts):
            return False
        if path.suffix.lower() not in SOURCE_SUFFIXES:
            return False
        return path.stat().st_size <= self.settings.max_file_bytes

    def _remove_changed_or_deleted_chunks(self, repo: RepositoryRecord, changes: list) -> None:
        changed_paths: set[str] = set()
        for change in changes:
            changed_paths.add(change.path)
            if getattr(change, "previous_path", None):
                changed_paths.add(change.previous_path)
        self.state.delete_chunks(self.state.chunk_ids_for_files(repo.id, changed_paths))

    def _prune_missing_files(self, repo: RepositoryRecord, repo_path: Path, source_files: list[Path]) -> None:
        current_paths = {str(path.relative_to(repo_path)) for path in source_files}
        indexed_paths = {
            self.state.chunks[chunk_id].file_path
            for chunk_id in self.state.repo_chunks.get(repo.id, [])
            if chunk_id in self.state.chunks
        }
        missing_paths = indexed_paths - current_paths
        self.state.delete_chunks(self.state.chunk_ids_for_files(repo.id, missing_paths))


def stable_chunk_id(repo_id: str, file_path: str, symbol_name: str | None, start_line: int) -> str:
    raw = f"{repo_id}:{file_path}:{symbol_name or 'text'}:{start_line}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def summarize_chunk(raw_text: str) -> str:
    first_line = next((line.strip() for line in raw_text.splitlines() if line.strip()), "")
    return first_line[:240] if first_line else "Empty or whitespace-only chunk."


def symbol_from_chunk(chunk: CodeChunk) -> SymbolRecord:
    return SymbolRecord(
        chunk_id=chunk.id,
        repo_id=chunk.repo_id,
        repo_name=chunk.repo_name,
        file_path=chunk.file_path,
        symbol_name=chunk.symbol_name or f"{chunk.file_path}:{chunk.start_line}",
        symbol_type=chunk.chunk_type,
        start_line=chunk.start_line,
        end_line=chunk.end_line,
    )


def extract_dependency_edges(chunk: CodeChunk, dependencies: list[str]) -> list[DependencyEdge]:
    return [
        DependencyEdge(source_chunk_id=chunk.id, target_symbol=dependency, relationship="references")
        for dependency in dependencies
    ]
