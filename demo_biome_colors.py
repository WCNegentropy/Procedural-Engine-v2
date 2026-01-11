"""Demonstrate biome color rendering pipeline.

This script shows that:
1. Terrain generates with biome data
2. Biome colors are assigned to mesh vertices
3. The rendering pipeline can use these colors
"""

import procengine_cpp as cpp
import numpy as np


def print_biome_color_palette():
    """Print the 16-biome color palette."""
    biome_names = [
        "Water", "Tundra", "BorealForest", "Snow", "ColdSwamp", "Glacier",
        "Steppe", "Forest", "Mountain", "Swamp", "Alpine", "DesertPlateau",
        "Savanna", "Mesa", "Jungle", "RainforestHighland"
    ]
    
    biome_colors = [
        (0.15, 0.35, 0.60), (0.75, 0.78, 0.80), (0.20, 0.35, 0.25),
        (0.95, 0.97, 1.00), (0.30, 0.35, 0.30), (0.85, 0.92, 0.98),
        (0.72, 0.68, 0.50), (0.25, 0.50, 0.20), (0.50, 0.45, 0.40),
        (0.35, 0.42, 0.30), (0.55, 0.58, 0.55), (0.85, 0.75, 0.55),
        (0.70, 0.62, 0.35), (0.75, 0.50, 0.35), (0.15, 0.55, 0.25),
        (0.20, 0.48, 0.30)
    ]
    
    print("\n" + "="*60)
    print("BIOME COLOR PALETTE")
    print("="*60)
    for i, (name, color) in enumerate(zip(biome_names, biome_colors)):
        r, g, b = color
        print(f"{i:2d}. {name:20s} RGB({r:.2f}, {g:.2f}, {b:.2f})")
    print("="*60 + "\n")


def demo_biome_colors():
    """Demonstrate the biome color rendering pipeline."""
    
    print_biome_color_palette()
    
    # Generate terrain with biomes
    print("Generating terrain with biomes...")
    result = cpp.generate_terrain_standalone(
        seed=42,
        size=128,
        octaves=6,
        macro_points=8,
        erosion_iters=500,
        return_slope=True
    )
    
    heightmap = result[0]
    biome_map = result[1]
    river_map = result[2]
    slope_map = result[3]
    
    print(f"✓ Terrain generated: {heightmap.shape}")
    print(f"  Height range: [{heightmap.min():.3f}, {heightmap.max():.3f}]")
    
    # Analyze biome distribution
    unique_biomes, counts = np.unique(biome_map, return_counts=True)
    print(f"\n✓ Biome distribution ({len(unique_biomes)} unique biomes):")
    biome_names = [
        "Water", "Tundra", "BorealForest", "Snow", "ColdSwamp", "Glacier",
        "Steppe", "Forest", "Mountain", "Swamp", "Alpine", "DesertPlateau",
        "Savanna", "Mesa", "Jungle", "RainforestHighland"
    ]
    for biome_id, count in sorted(zip(unique_biomes, counts), key=lambda x: -x[1])[:8]:
        percent = 100.0 * count / biome_map.size
        name = biome_names[biome_id] if biome_id < len(biome_names) else f"Unknown({biome_id})"
        print(f"  {name:20s}: {percent:5.1f}% ({count:5d} cells)")
    
    # Generate mesh with biome colors
    print("\nGenerating mesh with biome colors...")
    mesh = cpp.generate_terrain_mesh_with_biomes(heightmap, biome_map, 1.0, 30.0)
    
    print(f"✓ Mesh created:")
    print(f"  Vertices: {len(mesh.vertices):,}")
    print(f"  Triangles: {len(mesh.indices) // 3:,}")
    print(f"  Normals: {len(mesh.normals):,}")
    print(f"  Colors: {len(mesh.colors):,}")
    
    # Validate mesh
    assert mesh.validate(), "Mesh validation failed!"
    print(f"✓ Mesh validation passed")
    
    # Analyze color distribution
    print(f"\n✓ Vertex color statistics:")
    colors_array = np.array([(c.x, c.y, c.z) for c in mesh.colors])
    print(f"  Red   range: [{colors_array[:, 0].min():.3f}, {colors_array[:, 0].max():.3f}]")
    print(f"  Green range: [{colors_array[:, 1].min():.3f}, {colors_array[:, 1].max():.3f}]")
    print(f"  Blue  range: [{colors_array[:, 2].min():.3f}, {colors_array[:, 2].max():.3f}]")
    
    # Sample some colors
    print(f"\n✓ Sample vertex colors (first 5 vertices):")
    for i in range(5):
        c = mesh.colors[i]
        biome_idx = biome_map.flat[i]
        biome_name = biome_names[biome_idx] if biome_idx < len(biome_names) else f"Unknown({biome_idx})"
        print(f"  Vertex {i}: RGB({c.x:.3f}, {c.y:.3f}, {c.z:.3f}) <- {biome_name}")
    
    print("\n" + "="*60)
    print("SUCCESS: Biome Color Rendering Pipeline is Working!")
    print("="*60)
    print("\nWhat was fixed:")
    print("  1. Vertex struct now has color[4] field")
    print("  2. Mesh struct now has colors vector")
    print("  3. Terrain mesh generation assigns biome colors")
    print("  4. Vertex shader passes colors to fragment shader")
    print("  5. Fragment shader uses vertex colors with real lighting")
    print("  6. Python bridge passes biome_map to C++")
    print("\nResult:")
    print("  Terrain now renders with 16 distinct biome colors")
    print("  instead of flat magenta debug output!")
    print("="*60 + "\n")


if __name__ == "__main__":
    demo_biome_colors()
