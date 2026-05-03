from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field


class AssistantEvent(BaseModel):
    type: str
    message: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class IndexingRules(BaseModel):
    include_globs: list[str] = Field(default_factory=list)
    exclude_globs: list[str] = Field(default_factory=list)


class RepositoryCreate(BaseModel):
    name: str
    git_url: str
    default_branch: str = "main"
    visibility: Literal["public", "private"] = "public"
    credential_env_var: str | None = None
    indexing_rules: IndexingRules = Field(default_factory=IndexingRules)


class RepositoryRecord(RepositoryCreate):
    id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class IngestionRequest(BaseModel):
    confirm: bool = False
    base_ref: str | None = None
    webhook_commit: str | None = None


class GitWebhookRequest(BaseModel):
    repo_url: str
    before: str | None = None
    after: str | None = None
    ref: str | None = None


class IngestionStatus(BaseModel):
    id: str
    repo_id: str
    status: Literal["needs_permission", "running", "completed", "failed"]
    files_seen: int = 0
    chunks_indexed: int = 0
    errors: list[str] = Field(default_factory=list)
    assistant_events: list[AssistantEvent] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ChunkCandidate(BaseModel):
    file_path: str
    language: str
    symbol_name: str | None
    chunk_type: str
    start_line: int
    end_line: int
    raw_text: str
    ast_hash: str | None
    content_hash: str
    dependencies: list[str] = Field(default_factory=list)


class CodeChunk(ChunkCandidate):
    id: str
    repo_id: str
    repo_name: str
    summary: str
    embedding: list[float] = Field(default_factory=list)
    sparse_terms: dict[str, int] = Field(default_factory=dict)


class DependencyEdge(BaseModel):
    source_chunk_id: str
    target_symbol: str
    relationship: str


class SymbolRecord(BaseModel):
    chunk_id: str
    repo_id: str
    repo_name: str
    file_path: str
    symbol_name: str
    symbol_type: str
    start_line: int
    end_line: int


class GraphSnapshot(BaseModel):
    repo_id: str
    symbols: list[SymbolRecord]
    edges: list[DependencyEdge]


class Citation(BaseModel):
    repo: str
    file: str
    start_line: int
    end_line: int


class SearchResult(BaseModel):
    chunk_id: str
    repo_name: str
    file_path: str
    start_line: int
    end_line: int
    score: float
    source: Literal["dense", "sparse", "graph", "fused", "reranked"]
    retrieval_sources: list[str] = Field(default_factory=list)
    summary: str
    preview: str


class QueryRequest(BaseModel):
    question: str
    repo_ids: list[str] = Field(default_factory=list)
    top_k: int = 10


class QueryResponse(BaseModel):
    answer: str
    citations: list[Citation]
    assistant_events: list[AssistantEvent]
    retrieved_chunks: list[SearchResult]


class HealthResponse(BaseModel):
    status: str
    vector_store: str = "memory"
    graph_store: str = "memory"
