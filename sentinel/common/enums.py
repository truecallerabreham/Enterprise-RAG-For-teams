"""
Sentinel shared enumerations.

Defines the core enum types used across all modules to ensure consistent
department, source type, and visibility classification.
"""

from enum import Enum


class Department(str, Enum):
    """Company departments that own content and define access boundaries."""
    ENGINEERING = "engineering"
    HR = "hr"
    SALES = "sales"
    FINANCE_LEGAL = "finance_legal"
    SHARED = "shared"


class SourceType(str, Enum):
    """Types of knowledge sources that Sentinel can ingest."""
    PDF = "pdf"
    GITHUB = "github"
    SLACK = "slack"


class Visibility(str, Enum):
    """Content visibility classification for access control."""
    DEPARTMENT = "department"
    SHARED = "shared"


class SyncStatus(str, Enum):
    """Lifecycle states for sync jobs."""
    QUEUED = "queued"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    PAUSED = "paused"


class AnswerOutcome(str, Enum):
    """Outcome codes for answer orchestration decisions."""
    ANSWERED = "answered"
    CONFLICT_SPLIT = "conflict_split"
    REFUSED = "refused"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class AuthorityTier(str, Enum):
    """Authority ranking of source content."""
    OFFICIAL = "official"          # PDFs, policy documents
    OPERATIONAL = "operational"    # GitHub docs, runbooks
    DISCUSSION = "discussion"     # Slack threads, messages
