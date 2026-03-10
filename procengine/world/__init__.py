"""World generation systems.

This module contains all world generation components:
- terrain: Heightmap generation with FBM, erosion, biomes, rivers
- props: Rock, tree, building, creature descriptor generators
- materials: Procedural material graph generation
- world: Multi-chunk world assembly
- chunk: Chunk data structures and ChunkManager for infinite world support
"""

from procengine.world.terrain import generate_terrain_maps
from procengine.world.props import (
    generate_rock_descriptors,
    generate_tree_descriptors,
    generate_bush_descriptors,
    generate_pine_tree_descriptors,
    generate_dead_tree_descriptors,
    generate_fallen_log_descriptors,
    generate_boulder_cluster_descriptors,
    generate_flower_patch_descriptors,
    generate_mushroom_descriptors,
    generate_cactus_descriptors,
    generate_building_descriptors,
    generate_creature_descriptors,
)
from procengine.world.materials import generate_material_graph
from procengine.world.world import generate_chunk, generate_world
from procengine.world.chunk import (
    Chunk,
    ChunkCoord,
    ChunkManager,
    ChunkedHeightField,
)
from procengine.world.creature_templates import (
    CreatureTemplate,
    CREATURE_TEMPLATES,
    BIOME_SPECIES,
    generate_creature_from_template,
)

__all__ = [
    "generate_terrain_maps",
    "generate_rock_descriptors",
    "generate_tree_descriptors",
    "generate_bush_descriptors",
    "generate_pine_tree_descriptors",
    "generate_dead_tree_descriptors",
    "generate_fallen_log_descriptors",
    "generate_boulder_cluster_descriptors",
    "generate_flower_patch_descriptors",
    "generate_mushroom_descriptors",
    "generate_cactus_descriptors",
    "generate_building_descriptors",
    "generate_creature_descriptors",
    "generate_material_graph",
    "generate_chunk",
    "generate_world",
    # Chunk system
    "Chunk",
    "ChunkCoord",
    "ChunkManager",
    "ChunkedHeightField",
    # Creature templates
    "CreatureTemplate",
    "CREATURE_TEMPLATES",
    "BIOME_SPECIES",
    "generate_creature_from_template",
]
