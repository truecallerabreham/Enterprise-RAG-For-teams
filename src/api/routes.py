import json
from collections.abc import Generator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from src.ingestion.git_workspace import GitWorkspace
from src.ingestion.service import IngestionService
from src.models.schemas import (
    GitWebhookRequest,
    GraphSnapshot,
    HealthResponse,
    IngestionRequest,
    IngestionStatus,
    QueryRequest,
    QueryResponse,
    RepositoryCreate,
    RepositoryRecord,
)
from src.query.service import QueryService
from src.storage.memory import app_state

router = APIRouter()
ingestion_service = IngestionService(app_state)
query_service = QueryService(app_state)
git_workspace = GitWorkspace()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        vector_store=app_state.vector_store_status(),
        graph_store=app_state.settings.graph_provider,
    )


@router.post("/repositories", response_model=RepositoryRecord)
def register_repository(payload: RepositoryCreate) -> RepositoryRecord:
    valid, message = git_workspace.validate_remote(payload)
    if not valid:
        raise HTTPException(
            status_code=400,
            detail=(
                "Repository validation failed. Use a real reachable Git URL and branch. "
                "For private repositories, make sure the credential env var exists in the server process. "
                f"Git said: {message}"
            ),
        )
    return app_state.add_repository(payload)


@router.get("/repositories", response_model=list[RepositoryRecord])
def list_repositories() -> list[RepositoryRecord]:
    return list(app_state.repositories.values())


@router.delete("/repositories/{repo_id}", response_model=dict)
def delete_repository(repo_id: str) -> dict:
    deleted = app_state.delete_repository(repo_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Repository not found")
    return {"deleted": True}


@router.post("/repositories/{repo_id}/ingest", response_model=IngestionStatus)
def ingest_repository(repo_id: str, payload: IngestionRequest | None = None) -> IngestionStatus:
    request = payload or IngestionRequest()
    repo = app_state.repositories.get(repo_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="Repository not found")
    return ingestion_service.ingest_repository(repo, request)


@router.post("/webhooks/git", response_model=IngestionStatus)
def git_webhook(payload: GitWebhookRequest) -> IngestionStatus:
    repo = app_state.find_repository_by_url(payload.repo_url)
    if repo is None:
        raise HTTPException(status_code=404, detail="Repository not registered")
    return ingestion_service.ingest_repository(
        repo,
        IngestionRequest(confirm=True, base_ref=payload.before, webhook_commit=payload.after),
    )


@router.get("/ingestions/{job_id}", response_model=IngestionStatus)
def get_ingestion(job_id: str) -> IngestionStatus:
    job = app_state.ingestions.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Ingestion job not found")
    return job


@router.get("/repositories/{repo_id}/graph", response_model=GraphSnapshot)
def repository_graph(repo_id: str) -> GraphSnapshot:
    if repo_id not in app_state.repositories:
        raise HTTPException(status_code=404, detail="Repository not found")
    app_state.refresh_repository_counts(repo_id)
    symbols, edges = app_state.graph.snapshot(repo_id)
    return GraphSnapshot(repo_id=repo_id, symbols=symbols, edges=edges)


@router.post("/query", response_model=QueryResponse)
def query(payload: QueryRequest) -> QueryResponse:
    return query_service.answer(payload)


@router.post("/query/stream")
def query_stream(payload: QueryRequest) -> StreamingResponse:
    """Server-Sent Events endpoint that streams assistant events then the final answer."""

    def event_stream() -> Generator[str, None, None]:
        def sse(event_type: str, data: dict) -> str:
            return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"

        try:
            response = query_service.answer(payload)
            # Emit each assistant event in sequence
            for event in response.assistant_events:
                yield sse("step", {"type": event.type, "message": event.message})
            # Emit citations
            for i, citation in enumerate(response.citations):
                yield sse("citation", {
                    "index": i + 1,
                    "repo": citation.repo,
                    "file": citation.file,
                    "start_line": citation.start_line,
                    "end_line": citation.end_line,
                    "url": citation.url,
                })
            # Emit retrieved chunks
            for chunk in response.retrieved_chunks:
                yield sse("chunk", {
                    "chunk_id": chunk.chunk_id,
                    "repo_name": chunk.repo_name,
                    "file_path": chunk.file_path,
                    "start_line": chunk.start_line,
                    "end_line": chunk.end_line,
                    "score": chunk.score,
                    "retrieval_sources": chunk.retrieval_sources,
                    "summary": chunk.summary,
                    "url": chunk.url,
                })
            # Emit final answer
            yield sse("answer", {"text": response.answer})
            yield sse("done", {})
        except Exception as exc:
            yield sse("error", {"message": str(exc)})

    return StreamingResponse(event_stream(), media_type="text/event-stream")
