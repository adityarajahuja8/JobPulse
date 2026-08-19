"""Tests for the log-normal jitter pacing layer."""

from __future__ import annotations

import math
import statistics

import pytest

from acdyon.ingestion.pacing import sample_delays


class TestLogNormalDistribution:
    """Verify that delay samples follow a log-normal distribution, not uniform."""

    N = 2000   # Sample size — large enough for stable statistics.

    def test_mean_close_to_mu(self):
        """Sample mean should be within ~15% of the requested mu."""
        mu = 2.0
        delays = sample_delays(self.N, mu=mu, sigma=0.4)
        mean = statistics.mean(delays)
        # E[X] = exp(ln(mu) + sigma^2/2) ≈ mu * exp(sigma^2/2)
        # With sigma=0.4: correction ≈ exp(0.08) ≈ 1.083
        expected_mean = mu * math.exp(0.4**2 / 2)
        assert abs(mean - expected_mean) / expected_mean < 0.15, (
            f"Sample mean {mean:.3f} too far from expected {expected_mean:.3f}"
        )

    def test_all_positive(self):
        """Log-normal samples are always positive."""
        delays = sample_delays(self.N, mu=2.0)
        assert all(d > 0 for d in delays), "All delays must be positive"

    def test_not_uniform(self):
        """Distribution should NOT be uniform — standard deviation must be > 0."""
        delays = sample_delays(self.N, mu=2.0)
        stdev = statistics.stdev(delays)
        assert stdev > 0.1, f"Expected meaningful variance, got stdev={stdev:.4f}"

    def test_right_skewed(self):
        """Log-normal is right-skewed: mean > median."""
        delays = sample_delays(self.N, mu=3.0, sigma=0.5)
        mean = statistics.mean(delays)
        median = statistics.median(delays)
        assert mean > median, f"Expected mean ({mean:.3f}) > median ({median:.3f})"

    def test_sigma_controls_spread(self):
        """Higher sigma should produce higher standard deviation."""
        low_sigma = sample_delays(self.N, mu=2.0, sigma=0.2)
        high_sigma = sample_delays(self.N, mu=2.0, sigma=0.8)
        assert statistics.stdev(high_sigma) > statistics.stdev(low_sigma), (
            "Higher sigma should produce wider spread"
        )

    def test_crawl_delay_mu(self):
        """RemoteOK crawl delay: mu=65, samples should average above 60s."""
        delays = sample_delays(self.N, mu=65.0, sigma=0.3)
        mean = statistics.mean(delays)
        assert mean > 60.0, f"Mean {mean:.1f}s is below RemoteOK 60s crawl delay"

    def test_invalid_mu_raises(self):
        """mu <= 0 should raise ValueError."""
        import asyncio
        from acdyon.ingestion.pacing import jittered_sleep

        with pytest.raises(ValueError, match="mu must be positive"):
            asyncio.run(jittered_sleep(mu=0))
