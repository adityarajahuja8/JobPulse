"""Response anomaly / validation detection.

Design rationale (DESIGN.md §3):
    "every response is validated before it's trusted: expected content-length
    range, expected element counts, a basic 'does this look like a
    CAPTCHA/block page' check … Anomalies get retried with backoff a bounded
    number of times, then routed to the dead-letter queue … never silently
    dropped, never silently accepted as 'zero listings today.'"

    "parsing is never done with brittle absolute selectors … Every scrape
    run diffs its output shape against the last known-good schema; a shape
    mismatch … fails that run *loudly* into a dead-letter queue."
"""

from __future__ import annotations

from typing import Any

import structlog

from acdyon.ingestion.base import ValidationResult

log = structlog.get_logger(__name__)

# ── CAPTCHA / block-page heuristics ──────────────────────────────────────────

# Strings commonly found in CAPTCHA / firewall challenge pages.
_BLOCK_STRINGS = frozenset(
    {
        "captcha",
        "access denied",
        "403 forbidden",
        "cloudflare",
        "ray id",
        "just a moment",       # Cloudflare interstitial
        "perimeterx",
        "akamai",
        "bot detection",
        "please verify",
        "are you human",
        "unusual traffic",
        "automated requests",
        "enable javascript",   # common in JS challenge pages
        "ddos protection",
    }
)


def _looks_like_block_page(text: str) -> bool:
    """Return True if ``text`` contains known block/CAPTCHA phrases."""
    lowered = text.lower()
    return any(phrase in lowered for phrase in _BLOCK_STRINGS)


# ── Main validator ────────────────────────────────────────────────────────────


class ResponseValidator:
    """Validates raw API responses from a source adapter.

    Args:
        source_id:     Adapter source_id (e.g. "remoteok").
        min_items:     Minimum acceptable number of listings in the response.
        required_keys: Keys that every listing dict must contain.
    """

    def __init__(
        self,
        source_id: str,
        min_items: int = 1,
        required_keys: frozenset[str] = frozenset(),
    ) -> None:
        self.source_id = source_id
        self.min_items = min_items
        self.required_keys = required_keys

    def validate_raw(self, raw: list[dict[str, Any]]) -> ValidationResult:
        """Validate a list of raw listing dicts.

        Checks (in order):
        1. The response is a non-empty list.
        2. Item count meets the minimum threshold.
        3. Every item contains the required keys.

        Returns ValidationResult(ok=True) on pass.
        """
        if not isinstance(raw, list):
            reason = f"Expected list, got {type(raw).__name__}"
            log.warning("validator.type_mismatch", source=self.source_id, reason=reason)
            return ValidationResult(ok=False, reason=reason)

        if len(raw) < self.min_items:
            reason = f"Too few items: got {len(raw)}, expected >= {self.min_items}"
            log.warning("validator.too_few_items", source=self.source_id, reason=reason)
            return ValidationResult(ok=False, reason=reason)

        if self.required_keys:
            for i, item in enumerate(raw):
                missing = self.required_keys - set(item.keys())
                if missing:
                    reason = f"Item {i} missing required keys: {missing}"
                    log.warning(
                        "validator.missing_keys",
                        source=self.source_id,
                        reason=reason,
                    )
                    return ValidationResult(ok=False, reason=reason, details={"missing": list(missing)})

        log.debug("validator.ok", source=self.source_id, item_count=len(raw))
        return ValidationResult(ok=True)

    def validate_text_response(self, text: str) -> ValidationResult:
        """Check a raw text/HTML response for CAPTCHA or block-page signals.

        Used when the source unexpectedly returns HTML instead of JSON
        (a common bot-detection response pattern).
        """
        if _looks_like_block_page(text):
            reason = "Response looks like a CAPTCHA or block page"
            log.warning("validator.block_page", source=self.source_id)
            return ValidationResult(ok=False, reason=reason)
        return ValidationResult(ok=True)


# ── Schema-drift detection ────────────────────────────────────────────────────


def detect_schema_drift(
    parsed_docs: list[dict[str, Any]],
    known_fields: set[str],
    *,
    source_id: str,
    sample_size: int = 5,
) -> ValidationResult:
    """Compare the field set of parsed documents against a known-good snapshot.

    Drift is declared if required fields from the snapshot are absent from
    a majority of the sampled documents — indicating the source changed its
    response format.

    Args:
        parsed_docs:  Normalised documents as returned by adapter.parse().
        known_fields: Field set from the last known-good schema snapshot.
        source_id:    For log annotations.
        sample_size:  Number of docs to sample for the check.

    Returns ValidationResult(ok=False, reason="schema_drift") on drift.
    """
    if not parsed_docs or not known_fields:
        return ValidationResult(ok=True)

    sample = parsed_docs[:sample_size]
    missing_across_sample: dict[str, int] = {}

    for doc in sample:
        doc_fields = set(doc.keys())
        for field in known_fields:
            if field not in doc_fields:
                missing_across_sample[field] = missing_across_sample.get(field, 0) + 1

    # Drift: a previously present field is missing from > half the sample.
    drifted = {f for f, count in missing_across_sample.items() if count > len(sample) / 2}
    if drifted:
        reason = f"schema_drift: fields missing from majority of sample: {drifted}"
        log.error(
            "validator.schema_drift",
            source=source_id,
            drifted_fields=list(drifted),
        )
        return ValidationResult(ok=False, reason="schema_drift", details={"drifted": list(drifted)})

    return ValidationResult(ok=True)
