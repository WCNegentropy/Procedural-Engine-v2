"""Material graph specification utilities.

Provides deterministic generation of a small material graph consisting of
Noise, Warp, Blend, and PBR constant nodes.  The resulting graph is a
simple JSON-serializable dictionary suitable for hashing or transmission
to the C++ engine.
"""
from __future__ import annotations

from typing import Any, Dict

import numpy as np

from procengine.core.seed_registry import SeedRegistry

__all__ = ["generate_material_graph"]


def generate_material_graph(registry: SeedRegistry) -> Dict[str, Any]:
    """Return a deterministic material graph specification.

    Parameters
    ----------
    registry:
        Shared :class:`SeedRegistry` controlling randomness.
    """

    rng = registry.get_rng("material_graph")
    noise_node = {
        "type": "noise",
        "seed": int(rng.integers(0, 2**31)),
        "frequency": float(rng.uniform(0.5, 2.0)),
    }
    warp_node = {
        "type": "warp",
        "strength": float(rng.uniform(0.1, 1.0)),
        "input": "noise",
    }
    pbr_const_node = {
        "type": "pbr_const",
        "albedo": rng.random(3).tolist(),
        "roughness": float(rng.random()),
    }
    blend_node = {
        "type": "blend",
        "input_a": "warp",
        "input_b": "pbr_const",
        "factor": float(rng.random()),
    }
    graph = {
        "nodes": {
            "noise": noise_node,
            "warp": warp_node,
            "pbr_const": pbr_const_node,
            "blend": blend_node,
        },
        "output": "blend",
    }
    return graph
