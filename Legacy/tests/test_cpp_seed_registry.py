"""Tests for the C++ :class:`SeedRegistry` exposed via pybind11."""

from __future__ import annotations

import numpy as np
import pytest


procengine_cpp = pytest.importorskip("procengine_cpp")


def _splitmix64(seed_input: int) -> int:
    """Compute a single splitmix64 value from seed_input."""
    mask = 0xFFFFFFFFFFFFFFFF
    state = seed_input
    state = (state + 0x9E3779B97F4A7C15) & mask
    z = (state ^ (state >> 30)) * 0xBF58476D1CE4E5B9 & mask
    z = (z ^ (z >> 27)) * 0x94D049BB133111EB & mask
    return z ^ (z >> 31)


def _splitmix64_sequence(root: int, n: int) -> list[int]:
    """Return the first ``n`` subseeds using the splitmix64 algorithm."""

    state = root
    mask = 0xFFFFFFFFFFFFFFFF
    out = []
    for _ in range(n):
        state = (state + 0x9E3779B97F4A7C15) & mask
        z = (state ^ (state >> 30)) * 0xBF58476D1CE4E5B9 & mask
        z = (z ^ (z >> 27)) * 0x94D049BB133111EB & mask
        out.append(z ^ (z >> 31))
    return out


def test_named_subseeds_deterministic() -> None:
    """Named subseeds should be deterministic for same name."""

    registry = procengine_cpp.SeedRegistry(1234)
    seed1 = registry.get_subseed("terrain")
    seed2 = registry.get_subseed("terrain")
    assert seed1 == seed2, "Same name should return same subseed"

    seed3 = registry.get_subseed("physics")
    assert seed1 != seed3, "Different names should return different subseeds"


def test_named_subseeds_match_python() -> None:
    """C++ named subseeds should match Python SeedRegistry behavior."""

    root_seed = 1234

    # Python behavior: counter starts at 0, increments for each new name
    # seed_input = root_seed + counter, then splitmix64
    expected_terrain = _splitmix64(root_seed + 1)  # First name, counter=1
    expected_physics = _splitmix64(root_seed + 2)  # Second name, counter=2

    registry = procengine_cpp.SeedRegistry(root_seed)
    terrain_seed = registry.get_subseed("terrain")
    physics_seed = registry.get_subseed("physics")

    assert terrain_seed == expected_terrain
    assert physics_seed == expected_physics


def test_sequential_subseeds_match_reference() -> None:
    """C++ sequential subseeds should match a reference splitmix64 sequence."""

    registry = procengine_cpp.SeedRegistry(1234)
    expected = _splitmix64_sequence(1234, 5)
    result = [registry.get_subseed_sequential() for _ in range(5)]
    assert result == expected


def test_next_u64_reproducible() -> None:
    """Two registries with the same seed should produce identical sequences."""

    a = procengine_cpp.SeedRegistry(9876)
    b = procengine_cpp.SeedRegistry(9876)
    seq_a = [a.next_u64() for _ in range(5)]
    seq_b = [b.next_u64() for _ in range(5)]
    assert seq_a == seq_b

    c = procengine_cpp.SeedRegistry(1234)
    seq_c = [c.next_u64() for _ in range(5)]
    assert seq_a != seq_c


def test_root_seed_accessor() -> None:
    """root_seed() should return the original seed."""

    registry = procengine_cpp.SeedRegistry(42)
    assert registry.root_seed() == 42

