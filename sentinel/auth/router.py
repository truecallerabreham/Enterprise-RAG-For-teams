"""
Auth module router.

Handles authentication endpoints such as dev-mode token generation.
Business logic will be added in Track 3 (Identity and Access).
"""

from fastapi import APIRouter

router = APIRouter(prefix="/api/auth", tags=["auth"])
