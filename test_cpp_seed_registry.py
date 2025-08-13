"""Tests for the C++ :class:`SeedRegistry` exposed via pybind11."""

from __future__ import annotations

import numpy as np
import pytest


procengine_cpp = pytest.importorskip("procengine_cpp")


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


def test_subseeds_match_reference() -> None:
    """C++ subseeds should match a reference splitmix64 sequence."""

    registry = procengine_cpp.SeedRegistry(1234)
    expected = _splitmix64_sequence(1234, 5)
    result = [registry.get_subseed() for _ in range(5)]
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

