"""
Admin portal router.

Serves the admin operations dashboard — connector health, sync history,
retry/pause controls, and audit views.
Business logic will be added in Track 5 (Admin Portal Base).
"""

from fastapi import APIRouter

router = APIRouter(prefix="/api/admin", tags=["admin"])
