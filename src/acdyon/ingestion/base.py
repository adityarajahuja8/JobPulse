"""Abstract SourceAdapter — the common interface every ingestion adapter must implement.

Design rationale (from DESIGN.md §2):
    "the architecture treats scraping as one *replaceable* ingestion adapter
    behind a common interface … swapping in whatever legitimate channel exists
    behind the same interface, so downstream consumers of the data don't
    notice the source changed underneath them."

Adding a new source = subclass SourceAdapter, register it in runner.py.
Nothing else in the pipeline changes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ValidationResult:
    """Result of a single adapter response validation pass."""

    ok: bool
    reason: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


class SourceAdapter(ABC):
    """Base class for all ingestion source adapters.

    Subclasses must implement ``fetch_raw``, ``validate``, and ``parse``.
    The runner calls them in that order for every ingestion cycle.
    """

    # Stable, lowercase identifier used as the ``source`` field in MongoDB.
    source_id: str

    # Human-readable name for logs / CLI output.
    display_name: str

    @abstractmethod
    async def fetch_raw(self) -> list[dict[str, Any]]:
        """Fetch raw listing data from the source.

        Returns a list of raw dicts as returned by the source (before any
        normalisation). Raises on unrecoverable fetch error.
        """

    @abstractmethod
    def validate(self, raw: list[dict[str, Any]]) -> ValidationResult:
        """Validate the raw response.

        Checks for CAPTCHA/block pages, expected element counts, and
        minimum required fields. Returns a ValidationResult; does NOT
        raise — the runner decides what to do with a failed validation.
        """

    @abstractmethod
    def parse(self, raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Parse raw listing dicts into the normalised MongoDB document shape.

        Normalised shape (all fields):
            source          str   — adapter source_id
            external_id     str   — stable ID from the source
            title           str
            company         str
            location        str
            url             str   — direct link to listing (no redirects)
            tags            list[str]
            salary_min      int | None
            salary_max      int | None
            visa_sponsorship bool | None   (Arbeitnow; None for RemoteOK)
            four_day_week   bool | None   (Arbeitnow; None for RemoteOK)
            remote          bool | None
            posted_at       datetime | None
            raw             dict  — original dict preserved for debugging
        """
