"""Deterministic translation quality review (no LLM, no real API)."""

from .runner import run_review, validate_report_dict

__all__ = ["run_review", "validate_report_dict"]
