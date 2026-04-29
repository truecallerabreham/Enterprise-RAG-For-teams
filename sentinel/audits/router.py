"""
Audits module router.

Serves audit event views and decision trace access for admin operators.
Business logic will be added in Track 14 (Admin Operations & Audits).
"""

from fastapi import APIRouter

router = APIRouter(prefix="/api/audits", tags=["audits"])
