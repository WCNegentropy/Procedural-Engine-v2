"""Unit tests for deterministic material graph generation."""

from procengine.world.materials import generate_material_graph
from procengine.core.seed_registry import SeedRegistry


def test_generate_material_graph_deterministic():
    reg1 = SeedRegistry(5)
    reg2 = SeedRegistry(5)
    assert generate_material_graph(reg1) == generate_material_graph(reg2)


def test_generate_material_graph_structure():
    reg = SeedRegistry(0)
    graph = generate_material_graph(reg)
    assert set(graph["nodes"].keys()) == {"noise", "warp", "blend", "pbr_const"}
    assert graph["nodes"]["noise"]["type"] == "noise"
    assert graph["output"] == "blend"
