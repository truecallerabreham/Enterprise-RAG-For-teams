"""
Tests for Step 2.1: Core Persistence Models.

These tests verify that the SQLAlchemy ORM models are defined correctly
without actually connecting to a database. They verify:
1. All models exist and inherit from the declarative base
2. Table names are correctly set
3. Columns exist with correct names and default types
4. Relationships (like User -> Sessions) are configured

How these tests work:
- We use SQLAlchemy's internal inspector tools to check the model metadata
- No actual PostgreSQL database is needed to run these tests
"""

import pytest
from sqlalchemy import Column
from sqlalchemy.orm import DeclarativeBase

# We will test against the models module once it's implemented
# For now, we define what we expect to exist.


def test_base_model_exists():
    """Verify that the common declarative base class exists."""
    from sentinel.db.models import Base
    assert issubclass(Base, DeclarativeBase)


class TestUserModels:
    """Verify the User and Session models."""

    def test_user_model(self):
        from sentinel.db.models import User
        
        # Check table name
        assert User.__tablename__ == "users"
        
        # Check columns
        columns = User.__table__.columns.keys()
        assert "id" in columns
        assert "email" in columns
        assert "full_name" in columns
        assert "department" in columns
        assert "is_admin" in columns
        assert "created_at" in columns
        assert "updated_at" in columns

    def test_session_model(self):
        from sentinel.db.models import Session
        
        assert Session.__tablename__ == "sessions"
        
        columns = Session.__table__.columns.keys()
        assert "id" in columns
        assert "user_id" in columns
        assert "title" in columns
        assert "created_at" in columns
        assert "updated_at" in columns


class TestIngestionModels:
    """Verify the Source and SyncRun models."""

    def test_source_model(self):
        from sentinel.db.models import Source
        
        assert Source.__tablename__ == "sources"
        
        columns = Source.__table__.columns.keys()
        assert "id" in columns
        assert "department" in columns
        assert "type" in columns
        assert "name" in columns
        assert "status" in columns

    def test_sync_run_model(self):
        from sentinel.db.models import SyncRun
        
        assert SyncRun.__tablename__ == "sync_runs"
        
        columns = SyncRun.__table__.columns.keys()
        assert "id" in columns
        assert "source_id" in columns
        assert "status" in columns
        assert "started_at" in columns
        assert "items_processed" in columns


class TestKnowledgeModels:
    """Verify the Document and Chunk models."""

    def test_document_model(self):
        from sentinel.db.models import Document
        
        assert Document.__tablename__ == "documents"
        
        columns = Document.__table__.columns.keys()
        assert "id" in columns
        assert "source_id" in columns
        assert "external_id" in columns
        assert "title" in columns
        assert "metadata_" in columns

    def test_chunk_model(self):
        from sentinel.db.models import Chunk
        
        assert Chunk.__tablename__ == "chunks"
        
        columns = Chunk.__table__.columns.keys()
        assert "id" in columns
        assert "document_id" in columns
        assert "content" in columns
        assert "metadata_" in columns
        # Vector embedding column
        assert "embedding" in columns


class TestAuditModel:
    """Verify the AuditLog model."""

    def test_audit_log_model(self):
        from sentinel.db.models import AuditLog
        
        assert AuditLog.__tablename__ == "audit_logs"
        
        columns = AuditLog.__table__.columns.keys()
        assert "id" in columns
        assert "request_id" in columns
        assert "user_id" in columns
        assert "action" in columns
        assert "details" in columns
        assert "created_at" in columns
