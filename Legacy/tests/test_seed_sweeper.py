"""Tests for low-discrepancy seed generation utilities."""

import numpy as np

from seed_sweeper import generate_seed_batch


def test_generate_seed_batch_deterministic():
    seeds1 = generate_seed_batch(5)
    seeds2 = generate_seed_batch(5)
    assert np.array_equal(seeds1, seeds2)


def test_generate_seed_batch_range_and_type():
    seeds = generate_seed_batch(4, offset=2)
    assert seeds.dtype == np.uint64
    assert seeds.min() >= 0
    assert seeds.max() < np.iinfo(np.uint64).max
