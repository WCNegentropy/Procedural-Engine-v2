"""Unit tests for the :mod:`seed_registry` module."""

import numpy as np
import pytest

from seed_registry import SeedRegistry


def test_same_seed_same_rng_output():
    registry_a = SeedRegistry(42)
    registry_b = SeedRegistry(42)
    rng_a = registry_a.get_rng("terrain")
    rng_b = registry_b.get_rng("terrain")
    assert np.array_equal(rng_a.integers(0, 100, size=5), rng_b.integers(0, 100, size=5))


def test_subseed_uniqueness_per_name():
    registry = SeedRegistry(123)
    seed_a = registry.get_subseed("a")
    seed_b = registry.get_subseed("b")
    assert seed_a != seed_b


def test_rng_uses_pcg64():
    registry = SeedRegistry(77)
    rng = registry.get_rng("sub")
    assert type(rng.bit_generator) is np.random.PCG64


def test_spawn_creates_deterministic_registry():
    parent_a = SeedRegistry(1)
    parent_b = SeedRegistry(1)
    child_a = parent_a.spawn("chunk")
    child_b = parent_b.spawn("chunk")
    assert child_a.root_seed == child_b.root_seed
    rng_a = child_a.get_rng("test")
    rng_b = child_b.get_rng("test")
    assert np.array_equal(rng_a.integers(0, 100, size=4), rng_b.integers(0, 100, size=4))
