"""
Ingestion module router.

Manages source registration, sync job dispatch, and connector controls.
Business logic will be added in Track 6 (Source Registry & Sync Orchestration).
"""

from fastapi import APIRouter

router = APIRouter(prefix="/api/ingestion", tags=["ingestion"])
