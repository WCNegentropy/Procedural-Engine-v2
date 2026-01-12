"""Tests for deterministic prop descriptor generators."""

from procengine.world.props import (
    generate_building_descriptors,
    generate_creature_descriptors,
    generate_rock_descriptors,
    generate_tree_descriptors,
)
from procengine.core.seed_registry import SeedRegistry


def test_generate_rock_descriptors_deterministic():
    reg1 = SeedRegistry(1)
    reg2 = SeedRegistry(1)
    assert generate_rock_descriptors(reg1, 3) == generate_rock_descriptors(reg2, 3)


def test_generate_rock_descriptors_structure():
    reg = SeedRegistry(0)
    descs = generate_rock_descriptors(reg, 2, size=10.0)
    assert len(descs) == 2
    for d in descs:
        assert d["type"] == "rock"
        assert len(d["position"]) == 3
        assert all(0.0 <= p <= 10.0 for p in d["position"])
        assert 0.0 < d["radius"] <= 5.0


def test_generate_tree_descriptors_deterministic():
    reg1 = SeedRegistry(2)
    reg2 = SeedRegistry(2)
    assert generate_tree_descriptors(reg1, 2) == generate_tree_descriptors(reg2, 2)


def test_generate_tree_descriptors_structure():
    reg = SeedRegistry(3)
    trees = generate_tree_descriptors(reg, 1)
    assert len(trees) == 1
    tree = trees[0]
    assert tree["type"] == "tree"
    assert tree["axiom"] == "F"
    assert "F" in tree["rules"]
    assert tree["angle"] >= 0.0
    assert tree["iterations"] >= 0


def test_generate_building_descriptors_deterministic():
    reg1 = SeedRegistry(4)
    reg2 = SeedRegistry(4)
    assert generate_building_descriptors(reg1, 2) == generate_building_descriptors(
        reg2, 2
    )


def test_generate_building_descriptors_structure():
    reg = SeedRegistry(5)
    buildings = generate_building_descriptors(reg, 1, size=10.0)
    assert len(buildings) == 1
    building = buildings[0]
    assert building["type"] == "building"
    assert "root" in building
    root = building["root"]
    assert root["shape"] == "block"
    assert len(root["size"]) == 3


def test_generate_creature_descriptors_deterministic():
    reg1 = SeedRegistry(6)
    reg2 = SeedRegistry(6)
    assert generate_creature_descriptors(reg1, 1) == generate_creature_descriptors(
        reg2, 1
    )


def test_generate_creature_descriptors_structure():
    reg = SeedRegistry(7)
    creatures = generate_creature_descriptors(reg, 1)
    assert len(creatures) == 1
    creature = creatures[0]
    assert creature["type"] == "creature"
    assert len(creature["skeleton"]) >= 1
    assert len(creature["metaballs"]) >= 1
