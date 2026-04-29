"""
Sentinel Core Persistence Models.

Defines the SQLAlchemy ORM models representing the database schema.
We use SQLAlchemy 2.0 declarative syntax.

The models implemented here:
- User: An employee using the system.
- Session: A chat session containing history.
- Source: A registered data source (GitHub, Slack, etc.).
- SyncRun: Tracking of ingestion jobs.
- Document: A single ingested document.
- Chunk: A piece of a document, holding the vector embedding.
- AuditLog: Security-sensitive action record.

Note:
For JSON fields we use JSONB (PostgreSQL specific JSON).
For Vector fields we use pgvector's Vector type.
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Boolean, Integer, ForeignKey, DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB, UUID
from pgvector.sqlalchemy import Vector

from sentinel.common.enums import Department, SourceType


def utc_now():
    """Return the current UTC datetime."""
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """
    Common Base class for all Sentinel models.
    We don't put created_at/updated_at here because not all models need them
    (e.g., AuditLog only needs created_at, Source might not need them for now).
    """
    pass


class User(Base):
    """Represents an employee accessing the portal."""
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String, unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String)
    
    # Store enum as string
    department: Mapped[str] = mapped_column(String)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    # Relationships
    sessions = relationship("Session", back_populates="user", cascade="all, delete-orphan")


class Session(Base):
    """Represents a chat session where a user asks questions."""
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    # Relationships
    user = relationship("User", back_populates="sessions")


class Source(Base):
    """Represents a registered data source (e.g., a specific GitHub repo)."""
    __tablename__ = "sources"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    department: Mapped[str] = mapped_column(String)
    type: Mapped[str] = mapped_column(String)  # SourceType enum value
    name: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)  # e.g., 'active', 'error'

    # Relationships
    documents = relationship("Document", back_populates="source", cascade="all, delete-orphan")
    sync_runs = relationship("SyncRun", back_populates="source", cascade="all, delete-orphan")


class SyncRun(Base):
    """Tracks the background jobs that pull data from the sources."""
    __tablename__ = "sync_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sources.id"))
    status: Mapped[str] = mapped_column(String)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    items_processed: Mapped[int] = mapped_column(Integer, default=0)

    # Relationships
    source = relationship("Source", back_populates="sync_runs")


class Document(Base):
    """A raw document ingested from a source."""
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sources.id"))
    external_id: Mapped[str] = mapped_column(String, index=True)
    title: Mapped[str] = mapped_column(String)
    metadata_: Mapped[dict] = mapped_column(JSONB, default=dict)

    # Relationships
    source = relationship("Source", back_populates="documents")
    chunks = relationship("Chunk", back_populates="document", cascade="all, delete-orphan")


class Chunk(Base):
    """The smallest unit of knowledge containing the vector embedding."""
    __tablename__ = "chunks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id"))
    content: Mapped[str] = mapped_column(String)
    metadata_: Mapped[dict] = mapped_column(JSONB, default=dict)
    
    # Vector column. The size matches the Cohere English v3.0 embedding dimension (1024).
    embedding: Mapped[list[float]] = mapped_column(Vector(1024))

    # Relationships
    document = relationship("Document", back_populates="chunks")


class AuditLog(Base):
    """A record of security-sensitive events."""
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_id: Mapped[str] = mapped_column(String, index=True, nullable=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=True)
    action: Mapped[str] = mapped_column(String)
    details: Mapped[dict] = mapped_column(JSONB, default=dict)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
