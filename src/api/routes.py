from fastapi import APIRouter, HTTPException

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


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        vector_store=app_state.vector_store_status(),
        graph_store=app_state.settings.graph_provider,
    )


@router.post("/repositories", response_model=RepositoryRecord)
def register_repository(payload: RepositoryCreate) -> RepositoryRecord:
    return app_state.add_repository(payload)


@router.get("/repositories", response_model=list[RepositoryRecord])
def list_repositories() -> list[RepositoryRecord]:
    return list(app_state.repositories.values())


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
