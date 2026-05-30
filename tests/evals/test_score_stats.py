"""Tests for `ScoreStats.from_values` — percentile correctness.

Pre-M11, p5/p95 used `int(n * 0.05)` index lookup, which collapses to
min/max for small samples (the typical eval case). Post-M11 uses
`statistics.quantiles(method='inclusive')` for true linear-interpolated
percentiles. These tests pin the new behavior.
"""

from __future__ import annotations

import pytest

from protest.evals.types import ScoreStats


class TestEmptyAndSingleValue:
    def test_empty_returns_zeroed_stats(self) -> None:
        stats = ScoreStats.from_values("acc", [])
        assert stats.count == 0
        assert stats.mean == 0
        assert stats.p5 == 0
        assert stats.p95 == 0
        assert stats.min == 0
        assert stats.max == 0

    def test_single_value_collapses_percentiles(self) -> None:
        """One value → percentiles undefined; fall back to that value."""
        stats = ScoreStats.from_values("acc", [0.42])
        assert stats.count == 1
        assert stats.mean == pytest.approx(0.42)
        assert stats.median == pytest.approx(0.42)
        assert stats.p5 == pytest.approx(0.42)
        assert stats.p95 == pytest.approx(0.42)
        assert stats.min == pytest.approx(0.42)
        assert stats.max == pytest.approx(0.42)


class TestPercentilesNotCollapsedForSmallSamples:
    """Regression: with n=10 the old impl returned min/max for p5/p95."""

    def test_n_equals_10_p5_is_above_min(self) -> None:
        values = [float(i) for i in range(10)]  # 0..9
        stats = ScoreStats.from_values("acc", values)
        # Inclusive method interpolates: p5 of [0..9] is 0.45, p95 is 8.55
        assert stats.min == 0
        assert stats.p5 > stats.min
        assert stats.p5 == pytest.approx(0.45, abs=0.01)

    def test_n_equals_10_p95_is_below_max(self) -> None:
        values = [float(i) for i in range(10)]
        stats = ScoreStats.from_values("acc", values)
        assert stats.max == 9
        assert stats.p95 < stats.max
        assert stats.p95 == pytest.approx(8.55, abs=0.01)

    def test_n_equals_2_interpolates(self) -> None:
        """Inclusive percentiles work even for n=2 (interpolation)."""
        stats = ScoreStats.from_values("acc", [0.0, 1.0])
        assert stats.p5 == pytest.approx(0.05, abs=0.01)
        assert stats.p95 == pytest.approx(0.95, abs=0.01)


class TestPercentilesAccurateForLargeSamples:
    def test_n_equals_100_uniform_distribution(self) -> None:
        """For uniform 0..99, p5 ≈ 5 and p95 ≈ 95 (inclusive method)."""
        values = [float(i) for i in range(100)]
        stats = ScoreStats.from_values("acc", values)
        assert stats.p5 == pytest.approx(4.95, abs=0.1)
        assert stats.p95 == pytest.approx(94.05, abs=0.1)

    def test_unsorted_input_is_sorted_internally(self) -> None:
        """from_values must not depend on input order."""
        ordered = ScoreStats.from_values("a", [0.1, 0.2, 0.3, 0.4, 0.5])
        shuffled = ScoreStats.from_values("a", [0.3, 0.5, 0.1, 0.4, 0.2])
        assert ordered.p5 == pytest.approx(shuffled.p5)
        assert ordered.p95 == pytest.approx(shuffled.p95)
        assert ordered.median == pytest.approx(shuffled.median)


class TestBasicStatsStillCorrect:
    """Mean/median/min/max/count are unchanged."""

    def test_mean_and_median(self) -> None:
        stats = ScoreStats.from_values("acc", [1.0, 2.0, 3.0, 4.0, 5.0])
        assert stats.mean == pytest.approx(3.0)
        assert stats.median == pytest.approx(3.0)

    def test_min_max_count(self) -> None:
        stats = ScoreStats.from_values("acc", [0.2, 0.7, 0.1, 0.9, 0.5])
        assert stats.min == pytest.approx(0.1)
        assert stats.max == pytest.approx(0.9)
        assert stats.count == 5
