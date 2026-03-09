#!/usr/bin/env python3
"""Procedural Engine - Standalone Entry Point.

A hybrid Python/C++ procedural world generation engine with Vulkan graphics.
Generates 100% deterministic procedural worlds from a single root seed.

Usage:
    procedural-engine [OPTIONS]
    python main.py [OPTIONS]

Examples:
    # Generate a world with default settings
    procedural-engine --seed 42

    # Generate a larger terrain with erosion
    procedural-engine --seed 12345 --size 256 --erosion 100

    # Run in headless mode with output
    procedural-engine --seed 42 --headless --output world.json

    # Benchmark terrain generation
    procedural-engine --benchmark --iterations 10
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

# Import from procengine package
from procengine import (
    SeedRegistry,
    generate_terrain_maps,
    generate_rock_descriptors,
    generate_tree_descriptors,
    generate_building_descriptors,
    generate_creature_descriptors,
    generate_material_graph,
    RigidBody,
    step_physics,
    generate_world,
    GameRunner,
    RunnerConfig,
    Engine,
)

# Try to import C++ module
try:
    import procengine_cpp as cpp

    HAS_CPP = True
except ImportError:
    HAS_CPP = False
    cpp = None


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class EngineConfig:
    """Configuration for engine initialization."""

    seed: int = 42
    terrain_size: int = 64
    terrain_octaves: int = 6
    macro_points: int = 8
    erosion_iterations: int = 0
    chunk_count: tuple[int, int] = (2, 2)
    prop_counts: dict[str, int] | None = None
    headless: bool = True
    verbose: bool = False

    def __post_init__(self) -> None:
        if self.prop_counts is None:
            self.prop_counts = {
                "rocks": 10,
                "trees": 5,
                "buildings": 2,
                "creatures": 3,
            }


@dataclass
class WorldData:
    """Generated world data container."""

    seed: int
    terrain: dict[str, Any]
    props: dict[str, list[dict]]
    materials: dict[str, Any]
    chunks: dict[str, Any]
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "seed": self.seed,
            "terrain": {
                "height_shape": list(self.terrain["height"].shape),
                "height_min": float(self.terrain["height"].min()),
                "height_max": float(self.terrain["height"].max()),
                "biome_unique": int(len(np.unique(self.terrain["biome"]))),
                "river_coverage": float(self.terrain["river"].mean()),
            },
            "props": {k: len(v) for k, v in self.props.items()},
            "materials": self.materials,
            "chunks": {
                "count": len(self.chunks) if isinstance(self.chunks, dict) else 0,
            },
            "metadata": self.metadata,
        }


# =============================================================================
# Engine Implementation
# =============================================================================


class ProceduralEngine:
    """Main procedural engine class."""

    def __init__(self, config: EngineConfig) -> None:
        self.config = config
        self.registry = SeedRegistry(config.seed)
        self._cpp_engine = None

        if HAS_CPP:
            self._cpp_engine = cpp.Engine(config.seed)

        if config.verbose:
            print(f"[Engine] Initialized with seed {config.seed}")
            print(f"[Engine] C++ backend: {'Available' if HAS_CPP else 'Not available'}")

    def generate_world(self) -> WorldData:
        """Generate a complete world with terrain, props, and materials."""
        start_time = time.perf_counter()

        # Generate terrain
        terrain_start = time.perf_counter()
        terrain_data = self._generate_terrain()
        terrain_time = time.perf_counter() - terrain_start

        # Generate props
        props_start = time.perf_counter()
        props_data = self._generate_props()
        props_time = time.perf_counter() - props_start

        # Generate materials
        materials_start = time.perf_counter()
        materials_data = self._generate_materials()
        materials_time = time.perf_counter() - materials_start

        # Generate world chunks
        chunks_start = time.perf_counter()
        chunks_data = self._generate_chunks()
        chunks_time = time.perf_counter() - chunks_start

        total_time = time.perf_counter() - start_time

        metadata = {
            "engine_version": "1.0.0",
            "cpp_backend": HAS_CPP,
            "generation_time_ms": {
                "terrain": terrain_time * 1000,
                "props": props_time * 1000,
                "materials": materials_time * 1000,
                "chunks": chunks_time * 1000,
                "total": total_time * 1000,
            },
            "config": asdict(self.config),
        }

        if self.config.verbose:
            print(f"[Engine] World generated in {total_time * 1000:.2f}ms")

        return WorldData(
            seed=self.config.seed,
            terrain=terrain_data,
            props=props_data,
            materials=materials_data,
            chunks=chunks_data,
            metadata=metadata,
        )

    def _generate_terrain(self) -> dict[str, Any]:
        """Generate terrain maps."""
        if HAS_CPP and self._cpp_engine:
            # Use C++ backend
            result = self._cpp_engine.generate_terrain(
                size=self.config.terrain_size,
                octaves=self.config.terrain_octaves,
                macro_points=self.config.macro_points,
                erosion_iters=self.config.erosion_iterations,
                return_slope=True,
            )
            height, biome, river, slope = result
            return {
                "height": np.array(height),
                "biome": np.array(biome),
                "river": np.array(river),
                "slope": np.array(slope),
            }
        else:
            # Use Python backend
            result = generate_terrain_maps(
                self.registry,
                size=self.config.terrain_size,
                octaves=self.config.terrain_octaves,
                macro_points=self.config.macro_points,
                erosion_iters=self.config.erosion_iterations,
                return_slope=True,
            )
            height, biome, river, slope = result
            return {
                "height": height,
                "biome": biome,
                "river": river,
                "slope": slope,
            }

    def _generate_props(self) -> dict[str, list[dict]]:
        """Generate prop descriptors."""
        counts = self.config.prop_counts or {}

        rocks = generate_rock_descriptors(
            self.registry,
            counts.get("rocks", 10),
            size=float(self.config.terrain_size),
        )

        trees = generate_tree_descriptors(
            self.registry,
            counts.get("trees", 5),
        )

        buildings = generate_building_descriptors(
            self.registry,
            counts.get("buildings", 2),
        )

        creatures = generate_creature_descriptors(
            self.registry,
            counts.get("creatures", 3),
        )

        return {
            "rocks": rocks,
            "trees": trees,
            "buildings": buildings,
            "creatures": creatures,
        }

    def _generate_materials(self) -> dict[str, Any]:
        """Generate material graph."""
        return generate_material_graph(self.registry)

    def _generate_chunks(self) -> dict[str, Any]:
        """Generate world chunks."""
        width, height = self.config.chunk_count
        counts = self.config.prop_counts or {}
        return generate_world(
            self.registry,
            width=width,
            height=height,
            terrain_size=self.config.terrain_size,
            terrain_octaves=self.config.terrain_octaves,
            terrain_macro_points=self.config.macro_points,
            terrain_erosion_iters=self.config.erosion_iterations,
            rock_count=counts.get("rocks", 5),
            tree_count=counts.get("trees", 3),
            building_count=counts.get("buildings", 0),
            creature_count=counts.get("creatures", 0),
        )

    def run_physics_simulation(
        self,
        bodies: list[RigidBody],
        steps: int = 100,
        dt: float = 1.0 / 60.0,
    ) -> list[RigidBody]:
        """Run physics simulation on a set of bodies."""
        for _ in range(steps):
            step_physics(bodies, dt=dt)
        return bodies

    def get_state_hash(self) -> bytes:
        """Get deterministic state hash for verification."""
        if HAS_CPP and self._cpp_engine:
            return self._cpp_engine.snapshot_state(0)
        else:
            py_engine = Engine()
            return py_engine.snapshot_state(0)


# =============================================================================
# CLI Interface
# =============================================================================


def create_parser() -> argparse.ArgumentParser:
    """Create argument parser."""
    parser = argparse.ArgumentParser(
        prog="procedural-engine",
        description="Procedural Engine - Deterministic world generation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # Core options
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Root seed for deterministic generation (default: 42)",
    )
    parser.add_argument(
        "--size",
        type=int,
        default=64,
        help="Terrain size in pixels (default: 64)",
    )

    # Terrain options
    terrain_group = parser.add_argument_group("Terrain Options")
    terrain_group.add_argument(
        "--octaves",
        type=int,
        default=6,
        help="FBM noise octaves (default: 6)",
    )
    terrain_group.add_argument(
        "--macro-points",
        type=int,
        default=8,
        help="Voronoi macro plate points (default: 8)",
    )
    terrain_group.add_argument(
        "--erosion",
        type=int,
        default=0,
        help="Hydraulic erosion iterations (default: 0)",
    )

    # Props options
    props_group = parser.add_argument_group("Props Options")
    props_group.add_argument(
        "--rocks",
        type=int,
        default=10,
        help="Number of rock props (default: 10)",
    )
    props_group.add_argument(
        "--trees",
        type=int,
        default=5,
        help="Number of tree props (default: 5)",
    )
    props_group.add_argument(
        "--buildings",
        type=int,
        default=2,
        help="Number of building props (default: 2)",
    )
    props_group.add_argument(
        "--creatures",
        type=int,
        default=3,
        help="Number of creature props (default: 3)",
    )

    # World options
    world_group = parser.add_argument_group("World Options")
    world_group.add_argument(
        "--chunks-x",
        type=int,
        default=2,
        help="Number of chunks in X direction (default: 2)",
    )
    world_group.add_argument(
        "--chunks-y",
        type=int,
        default=2,
        help="Number of chunks in Y direction (default: 2)",
    )

    # Output options
    output_group = parser.add_argument_group("Output Options")
    output_group.add_argument(
        "--output",
        "-o",
        type=Path,
        help="Output file for world data (JSON format)",
    )
    output_group.add_argument(
        "--headless",
        action="store_true",
        default=False,
        help="Run in headless mode (no graphics window)",
    )
    output_group.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose output",
    )

    # Special modes
    special_group = parser.add_argument_group("Special Modes")
    special_group.add_argument(
        "--generate-only",
        action="store_true",
        help="Only generate world data, don't run game (for CI/tools)",
    )
    special_group.add_argument(
        "--benchmark",
        action="store_true",
        help="Run performance benchmark",
    )
    special_group.add_argument(
        "--iterations",
        type=int,
        default=10,
        help="Benchmark iterations (default: 10)",
    )
    special_group.add_argument(
        "--verify",
        action="store_true",
        help="Verify determinism (run twice, compare hashes)",
    )
    special_group.add_argument(
        "--version",
        action="version",
        version="%(prog)s 1.0.0",
    )

    return parser


def run_benchmark(config: EngineConfig, iterations: int) -> None:
    """Run performance benchmark."""
    print(f"Running benchmark with {iterations} iterations...")
    print(f"Config: seed={config.seed}, size={config.terrain_size}")
    print("-" * 60)

    times: list[float] = []

    for i in range(iterations):
        start = time.perf_counter()
        engine = ProceduralEngine(config)
        world = engine.generate_world()
        elapsed = time.perf_counter() - start
        times.append(elapsed)

        if config.verbose:
            print(f"  Iteration {i + 1}: {elapsed * 1000:.2f}ms")

    avg_time = sum(times) / len(times)
    min_time = min(times)
    max_time = max(times)

    print("-" * 60)
    print(f"Results ({iterations} iterations):")
    print(f"  Average: {avg_time * 1000:.2f}ms")
    print(f"  Min:     {min_time * 1000:.2f}ms")
    print(f"  Max:     {max_time * 1000:.2f}ms")
    print(f"  C++ Backend: {'Yes' if HAS_CPP else 'No'}")


def verify_determinism(config: EngineConfig) -> bool:
    """Verify that generation is deterministic."""
    print("Verifying determinism...")
    print(f"Generating world twice with seed {config.seed}...")

    # Generate first world
    engine1 = ProceduralEngine(config)
    world1 = engine1.generate_world()

    # Generate second world with same seed
    engine2 = ProceduralEngine(config)
    world2 = engine2.generate_world()

    # Compare terrain
    terrain_match = (
        np.array_equal(world1.terrain["height"], world2.terrain["height"])
        and np.array_equal(world1.terrain["biome"], world2.terrain["biome"])
        and np.array_equal(world1.terrain["river"], world2.terrain["river"])
    )

    # Compare props
    props_match = world1.props == world2.props

    # Compare materials
    materials_match = world1.materials == world2.materials

    all_match = terrain_match and props_match and materials_match

    print("-" * 60)
    print(f"Terrain match:   {'PASS' if terrain_match else 'FAIL'}")
    print(f"Props match:     {'PASS' if props_match else 'FAIL'}")
    print(f"Materials match: {'PASS' if materials_match else 'FAIL'}")
    print("-" * 60)
    print(f"Determinism:     {'VERIFIED' if all_match else 'FAILED'}")

    return all_match


def main() -> int:
    """Main entry point."""
    parser = create_parser()
    args = parser.parse_args()

    # Build config
    config = EngineConfig(
        seed=args.seed,
        terrain_size=args.size,
        terrain_octaves=args.octaves,
        macro_points=args.macro_points,
        erosion_iterations=args.erosion,
        chunk_count=(args.chunks_x, args.chunks_y),
        prop_counts={
            "rocks": args.rocks,
            "trees": args.trees,
            "buildings": args.buildings,
            "creatures": args.creatures,
        },
        headless=args.headless,
        verbose=args.verbose,
    )

    # Print header
    print("=" * 60)
    print("  Procedural Engine v1.0.0")
    print("  Deterministic World Generation")
    print("=" * 60)
    print(f"  C++ Backend: {'Available' if HAS_CPP else 'Python-only'}")
    print("=" * 60)
    print()

    # Handle special modes
    if args.benchmark:
        run_benchmark(config, args.iterations)
        return 0

    if args.verify:
        success = verify_determinism(config)
        return 0 if success else 1

    # Generate-only mode (for CI/tools)
    if args.generate_only or args.output:
        print(f"Generating world with seed {config.seed}...")
        engine = ProceduralEngine(config)
        world = engine.generate_world()

        # Print summary
        summary = world.to_dict()
        print()
        print("World Summary:")
        print("-" * 40)
        print(f"  Seed: {summary['seed']}")
        print(f"  Terrain: {summary['terrain']['height_shape'][0]}x{summary['terrain']['height_shape'][1]}")
        print(f"    Height range: [{summary['terrain']['height_min']:.3f}, {summary['terrain']['height_max']:.3f}]")
        print(f"    Biome types: {summary['terrain']['biome_unique']}")
        print(f"    River coverage: {summary['terrain']['river_coverage'] * 100:.1f}%")
        print(f"  Props:")
        for prop_type, count in summary["props"].items():
            print(f"    {prop_type}: {count}")
        print(f"  Generation time: {summary['metadata']['generation_time_ms']['total']:.2f}ms")

        # Save output if requested
        if args.output:
            output_path = Path(args.output)
            with open(output_path, "w") as f:
                json.dump(summary, f, indent=2)
            print()
            print(f"World data saved to: {output_path}")

        print()
        print("Done!")
        return 0

    # Normal mode: Run the game!
    # The game now boots into a main menu where the user can configure
    # the world seed and other parameters before generation begins.
    print("Launching Procedural Engine...")
    print()

    runner_config = RunnerConfig(
        window_title="Procedural Engine v2",
        window_width=1280,
        window_height=720,
        headless=args.headless,
        world_seed=config.seed,  # Default seed; overridden by world creation screen
        enable_debug=args.verbose,
    )

    runner = GameRunner(runner_config)

    try:
        runner.run()
    except KeyboardInterrupt:
        print("\nGame interrupted by user.")
    except Exception as e:
        print(f"\nGame error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        # Keep window open on error so user can see message
        if sys.platform == "win32":
            input("\nPress Enter to exit...")
        return 1

    print("\nThanks for playing!")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()
        if sys.platform == "win32":
            input("\nPress Enter to exit...")
        sys.exit(1)
