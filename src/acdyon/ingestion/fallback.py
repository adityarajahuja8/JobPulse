"""Fallback ladder orchestration.

Design rationale (DESIGN.md §2, steps 1–5):
    1. Back off that identity entirely (cool-down, not retry-immediately).
    2. Rotate to a fresh identity/proxy for the remaining queue.
    3. Drop request volume site-wide and re-check block status after a delay.
    4. If the source stays blocked, fail over to any secondary/mirror source.
    5. If nothing legitimate is left, pause and alert a human — never silently
       keep hammering.

Key design principle: the ladder DE-ESCALATES before it fails over.
It never escalates or routes around a block by defeating bot-detection controls.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog

from acdyon.config import settings

log = structlog.get_logger(__name__)


# ── Identity / proxy state ────────────────────────────────────────────────────


@dataclass
class IdentityState:
    """Tracks block/cooldown state for a single proxy identity.

    An "identity" in the DESIGN.md sense = a (proxy, cookie jar, UA) tuple.
    For the demo without proxies this degrades to a single default identity.
    """

    identity_id: str
    is_cooling_down: bool = False
    cooldown_until: datetime | None = None
    block_count: int = 0

    def mark_blocked(self, cooldown_seconds: float = 300.0) -> None:
        """Put this identity into a cooldown period."""
        self.is_cooling_down = True
        self.cooldown_until = datetime.now(timezone.utc) + timedelta(seconds=cooldown_seconds)
        self.block_count += 1
        log.warning(
            "fallback.identity_blocked",
            identity=self.identity_id,
            cooldown_seconds=cooldown_seconds,
            total_blocks=self.block_count,
        )

    @property
    def is_available(self) -> bool:
        """True if this identity is ready to use."""
        if not self.is_cooling_down:
            return True
        if datetime.now(timezone.utc) >= (self.cooldown_until or datetime.min.replace(tzinfo=timezone.utc)):
            # Cooldown expired — reset.
            self.is_cooling_down = False
            self.cooldown_until = None
            return True
        return False


# ── Fallback orchestrator ─────────────────────────────────────────────────────


@dataclass
class FallbackOrchestrator:
    """Implements the five-step fallback ladder from DESIGN.md §2.

    Args:
        source_id:          Adapter source_id (for logs).
        identities:         Pool of IdentityState objects. The demo runs with
                            a single default identity (no real proxy rotation).
        global_throttle_s:  How long (seconds) to sleep in step 3 before
                            re-checking block status.
        max_ladder_attempts: How many times to cycle the ladder before giving up
                            and alerting.
    """

    source_id: str
    identities: list[IdentityState] = field(default_factory=list)
    global_throttle_s: float | None = None
    max_ladder_attempts: int = 3

    def __post_init__(self) -> None:
        if not self.identities:
            # Single default identity for demo mode (no proxies).
            self.identities = [IdentityState(identity_id="default")]
        if self.global_throttle_s is None:
            self.global_throttle_s = settings.global_throttle_seconds

    # ── Public entry point ────────────────────────────────────────────────────

    async def handle_block(self, *, context: dict[str, Any] | None = None) -> bool:
        """Run the fallback ladder after a block/anomaly is detected.

        Returns True if recovery succeeded (a new identity is available),
        False if all options are exhausted and a human must intervene.

        Steps 1–5 are executed in order. Steps 4–5 are signalled via return
        value — the runner decides whether to try the next adapter in chain.
        """
        ctx = context or {}
        log.warning("fallback.ladder_start", source=self.source_id, **ctx)

        for attempt in range(1, self.max_ladder_attempts + 1):
            log.info("fallback.ladder_attempt", source=self.source_id, attempt=attempt)

            # Step 1: Back off current identity.
            self._step1_backoff_current()

            # Step 2: Rotate to a fresh identity.
            next_identity = self._step2_rotate()
            if next_identity:
                log.info(
                    "fallback.rotated",
                    source=self.source_id,
                    identity=next_identity.identity_id,
                )
                return True  # Recovery succeeded — caller continues with new identity.

            # Step 3: No fresh identity available — global throttle and re-check.
            log.warning(
                "fallback.global_throttle",
                source=self.source_id,
                sleep_s=self.global_throttle_s,
            )
            await asyncio.sleep(self.global_throttle_s)

            next_identity = self._step2_rotate()
            if next_identity:
                return True

        # Step 4 & 5: Nothing left — caller must fail over to secondary source or alert.
        self._step5_alert()
        return False

    # ── Ladder steps ──────────────────────────────────────────────────────────

    def _step1_backoff_current(self) -> None:
        """Step 1: Put the current (first available) identity into cooldown."""
        for identity in self.identities:
            if identity.is_available:
                identity.mark_blocked()
                return

    def _step2_rotate(self) -> IdentityState | None:
        """Step 2: Return the next available identity, or None if all are cooling down."""
        for identity in self.identities:
            if identity.is_available:
                log.debug("fallback.identity_available", identity=identity.identity_id)
                return identity
        return None

    def _step5_alert(self) -> None:
        """Step 5: Log CRITICAL alert. In production this would page a human."""
        log.critical(
            "fallback.exhausted",
            source=self.source_id,
            message=(
                "All fallback attempts exhausted. "
                "Source is paused. Human review required. "
                "Do NOT retry automatically — see DESIGN.md §2 step 5."
            ),
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    @property
    def all_cooling_down(self) -> bool:
        """True if every identity in the pool is currently cooling down."""
        return all(not i.is_available for i in self.identities)
