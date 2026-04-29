"""
Employee portal router.

Serves the employee query workspace — sessions, question submission,
answer display, and evidence views.
Business logic will be added in Track 4 (Employee Portal Base).
"""

from fastapi import APIRouter

router = APIRouter(prefix="/api/portal", tags=["portal"])
