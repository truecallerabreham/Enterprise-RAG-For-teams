"""
Retrieval module router.

Handles scoped retrieval requests — accepts auth scope and query,
returns ranked evidence sets.
Business logic will be added in Track 11 (Retrieval).
"""

from fastapi import APIRouter

router = APIRouter(prefix="/api/retrieval", tags=["retrieval"])
