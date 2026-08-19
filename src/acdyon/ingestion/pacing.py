"""Log-normal jitter pacing.

Design rationale (DESIGN.md §2):
    "requests per identity are spaced with jittered, log-normal delays
    (not uniform sleep()), capped well under what a fast human reader
    would do, with occasional longer 'went and did something else' pauses."

Why log-normal?
- Always positive (sleep duration can't be negative).
- Right-skewed: most delays are close to the mean, but occasionally a longer
  pause occurs naturally — matching human reading behaviour.
- Unlike uniform jitter, the variance is parameterised independently from
  the mean, giving fine-grained control over how "erratic" the pacing looks.

Usage:
    await jittered_sleep(mu=2.0)          # ~2-second mean delay
    await jittered_sleep(mu=60.0)         # RemoteOK crawl delay
    await long_pause()                    # occasional "went AFK" pause
"""

from __future__ import annotations

import asyncio
import math
import random

import structlog

log = structlog.get_logger(__name__)


async def jittered_sleep(
    mu: float = 2.0,
    sigma: float = 0.4,
    *,
    label: str = "pacing",
) -> float:
    """Sleep for a log-normally distributed duration.

    Args:
        mu:    Desired mean delay in seconds (must be > 0).
        sigma: Shape parameter controlling spread.
               Larger sigma → more variance, longer right tail.
        label: Annotation for the structured log line.

    Returns:
        Actual sleep duration in seconds.
    """
    if mu <= 0:
        raise ValueError(f"mu must be positive, got {mu}")

    # lognormvariate(mu_log, sigma) where mu_log = ln(mu) gives E[X] ≈ mu
    # (exact: E[X] = exp(mu_log + sigma²/2), so there's a slight upward bias
    # which is intentional — we'd rather sleep a touch longer than shorter).
    delay = random.lognormvariate(math.log(mu), sigma)
    log.debug("pacing.sleep", label=label, duration_s=round(delay, 2))
    await asyncio.sleep(delay)
    return delay


async def long_pause(
    mu: float = 120.0,
    sigma: float = 0.5,
    *,
    label: str = "long_pause",
) -> float:
    """Occasional extended pause simulating "went and did something else".

    Default mean: 2 minutes. Call this after every N normal requests to
    introduce the kind of irregular long gaps a human session produces.
    """
    return await jittered_sleep(mu=mu, sigma=sigma, label=label)


def sample_delays(n: int, mu: float = 2.0, sigma: float = 0.4) -> list[float]:
    """Return a list of n delay samples (synchronous, for testing/analysis)."""
    return [
        random.lognormvariate(math.log(mu), sigma) for _ in range(n)
    ]
