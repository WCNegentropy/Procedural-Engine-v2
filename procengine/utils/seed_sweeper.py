"""Seed mining utilities using a low-discrepancy sequence.

This module provides :func:`generate_seed_batch` which returns
``uint64`` seeds derived from a one-dimensional Sobol sequence
(implemented via a Van der Corput radical inverse in base 2).
The sequence is deterministic and free of global RNG state,
meeting the determinism requirements specified in ``AGENTS.md``.

Example
-------
>>> generate_seed_batch(3)
array([                    0, 9223372036854775808, 4611686018427387904],
      dtype=uint64)
"""
from __future__ import annotations

import numpy as np

__all__ = ["generate_seed_batch"]


_MAX_UINT64 = np.iinfo(np.uint64).max


def _van_der_corput(index: int) -> float:
    """Return the Van der Corput radical inverse of ``index`` in base 2.

    The result lies in ``[0, 1)`` and forms the one-dimensional Sobol
    sequence used to generate low-discrepancy seeds.
    """

    value = 0.0
    denom = 1.0
    i = index
    while i:
        denom *= 2.0
        value += (i & 1) / denom
        i >>= 1
    return value


def generate_seed_batch(count: int, *, offset: int = 0) -> np.ndarray:
    """Return ``count`` deterministic seeds as ``np.uint64``.

    Parameters
    ----------
    count:
        Number of seeds to generate. Must be non-negative.
    offset:
        Starting index within the Sobol sequence.
    """

    if count < 0:
        raise ValueError("count must be non-negative")

    seeds = np.empty(count, dtype=np.uint64)
    for idx in range(count):
        vdc = _van_der_corput(idx + offset)
        seeds[idx] = np.uint64(vdc * _MAX_UINT64)
    return seeds


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate deterministic seeds")
    parser.add_argument("count", nargs="?", type=int, default=10, help="number of seeds")
    parser.add_argument("--offset", type=int, default=0, help="sequence offset")
    args = parser.parse_args()

    for seed in generate_seed_batch(args.count, offset=args.offset):
        print(int(seed))
