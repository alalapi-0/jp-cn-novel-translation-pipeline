"""Plan-only alignment for user-supplied translation revisions."""

from .aligner import align_revisions, normalize_text
from .plan import build_sync_plan, validate_sync_plan

__all__ = ["align_revisions", "build_sync_plan", "normalize_text", "validate_sync_plan"]
