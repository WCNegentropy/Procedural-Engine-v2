# AGENTS.md — Procedural Game Engine (Flagship Studio Ecosystem)

## Purpose
This document binds every human contributor and automated agent (e.g., ChatGPT Codex, CI bots) to the core constraints, architecture, and best-practice workflow defined in **Procedural Game Engine – Architecture v1** (see `/docs/Architecture_v1.md`).
Paste this file into the root of the game-studio repository so that any context-aware tools inherit these rules automatically.

---

## 1 · Guiding Principles
- **Determinism First** — All runtime output must be a pure function of the designated seeds and engine version. No hidden randomness or non-replayable state.
- **Hybrid Discipline** — Python ≙ author-time generators & tooling; C++ ≙ real-time execution. Cross only at the defined FFI API.
- **One Source of Truth** — The RootSeed governs every subsystem via the SeedRegistry; diverging PRNGs are forbidden.
- **Immutability After Hand-Off** — Once a buffer crosses the Python → C++ boundary, its contents are read-only. C++ mutates runtime state via ECS, never the original generator data.
- **Fail Fast, Fail Loud** — Any determinism hash mismatch, FPS regression, or physics NaN terminates the build or CI run.

---

## 2 · Language Ownership Matrix

| Subsystem         | Python Responsibilities | C++ Responsibilities |
|-------------------|--------------------------|-----------------------|
| **Seeds & PRNG**  | Call `SeedRegistry.get_subseed()`; never instantiate local RNGs. | Master `SeedRegistry`, expose PCG64 stream to Python via FFI. |
| **Terrain**       | Height/Biome/River mask generation, macro-plates, simplex FBM, biome LUT ✅ | GeoClipmap mesh, GPU erosion, collider heightfield. |
| **Props & Creatures** | Generate JSON descriptors (CSG trees, L-systems, genomes). | Mesh synthesis, LODs, skeleton rigs, GPU upload. |
| **Materials**     | Emit material graph DSL (JSON). | DSL→SPIR-V compile, virtual texture paging. |
| **Physics**       | 2D reference solver + broad-phase/heightfield ✅ | Bullet-style solver, fluid voxels, wind fields. |
| **Testing/Tooling** | Seed mining, dashboards, live editors. | Headless mode, hot-reload endpoint. |

> Do **NOT** add gameplay logic that requires per-frame Python execution. Script only large-grain events.

---

## 3 · Determinism Contract
- Use **PCG64** for every random sample.
- Fixed Δt = 1/60 s physics step.
- **SHA-256** hash every buffer passed over FFI and assert equality on C++ side.
- Regression test hashes at frames 0, 100, 500 in CI.

---

## 4 · FFI API Surface (Canonical)
```python
Engine.enqueue_heightmap(memview h16, memview biome8, memview river1)
Engine.enqueue_prop_descriptor(list[dict])
Engine.hot_reload(uint64 descriptorHash)
Engine.step(float dt)
Engine.reset()
Engine.snapshot_state(frame:int) -> bytes   # returns deterministic hash
```

---

## 5 · Best Practices & CI Pipeline
- Adhere to PEP 8 style and type annotate new Python code.
- Run `pytest` and ensure all tests pass before submitting a change.
- Update `TEST_RESULTS.md` with the latest `pytest` results after meaningful changes.
- The GitHub Actions workflow runs tests on Python 3.10 and 3.11 and builds the package; keep these jobs green.
- Each commit must leave the repository in a clean state with all checks passing.
- Maintain the root `requirements.txt` with all core dependencies (currently `numpy` and `pytest`).
- Respect the repository `.gitignore`; avoid committing build artifacts or virtual environments.

---

## 6 · Implementation Status

### Python Reference Implementation
- ✅ Deterministic buffer hashing and state snapshot API (`engine.py`)
- ✅ Hot-reload descriptor hash tracking (`engine.py`)
- ✅ State hash regression helper (`Engine.run_and_snapshot`)
- ✅ Reset to initial state (`Engine.reset`)
- ✅ Deterministic rock descriptor generator (`props.py`)
- ✅ Material graph specification emitter (`materials.py`)
- ✅ Deterministic tree L-system descriptor generator (`props.py`)
- ✅ Deterministic building shape grammar descriptor generator (`props.py`)
- ✅ Deterministic creature metaball + skeleton descriptor generator (`props.py`)
- ✅ Deterministic 2D sequential impulse physics solver (`physics.py`)
- ✅ Uniform grid broad-phase and heightfield proxy (`physics.py`)
- ✅ Configurable gravity and damping in physics solver (`physics.py`)
- ✅ Hierarchical seed registry spawning (`seed_registry.py`)
- ✅ Multi-chunk world generator with macro plates and erosion (`world.py`)
- ✅ Deterministic terrain generation (FBM, biomes, erosion, slope) (`terrain.py`)
- ✅ Deterministic Sobol seed batch generator (`seed_sweeper.py`)

### C++ Runtime Implementation
- ✅ Full terrain generation system (macro-plates, FBM, hydraulic erosion, biomes, rivers, slopes)
- ✅ Props mesh generation (rocks, trees, buildings, creatures with LODs)
- ✅ Material graph compiler (GLSL generation, SPIR-V compilation, shader cache)
- ✅ Physics system (sequential impulse solver, heightfield collider, deterministic simulation)
- ⚠️ Graphics system (see **Graphics Implementation Status** below)
- ✅ Hot-reload infrastructure (descriptor caching, dirty-state tracking, rebuild queue)
- ✅ SeedRegistry with PCG64 PRNG and deterministic sub-seeding
- ✅ Buffer hashing and state snapshot API matching Python spec

### Phase 2 Game Systems (Python)
- ✅ GameWorld, Entity hierarchy, Event system (`game_api.py`)
- ✅ Full behavior tree system with decorators (`behavior_tree.py`)
- ✅ Input abstraction and camera system (`player_controller.py`)
- ✅ JSON data loading for NPCs, quests, items (`data_loader.py`)
- ✅ Game loop orchestration with physics (`game_runner.py`)
- ✅ UI system with headless testing support (`ui_system.py`)
- ✅ Graphics bridge with headless fallback (`graphics_bridge.py`)

---

## 7 · Graphics Implementation Status

The Vulkan graphics backend has core infrastructure but rendering is not fully operational.
Headless mode is fully functional for testing and CI.

| Component | File:Line | Current State | What's Missing |
|-----------|-----------|---------------|----------------|
| `draw_mesh()` | cpp/graphics.cpp:1020-1026 | Stats only | `vkCmdDraw*` calls, pipeline/descriptor binding |
| `create_pipeline()` | cpp/graphics.cpp:769-801 | Layout only | VkPipeline creation, shader module binding |
| Render passes | cpp/graphics.cpp:1050-1080 | Forward only | Depth prepass, post-process pass |
| Framebuffers | cpp/graphics.cpp:1082-1099 | Images only | VkFramebuffer objects |
| Material pipeline | cpp/graphics.cpp:1208 | Null render pass | Valid render pass binding |
| `clear_lights()` | graphics_bridge.py:564 | Python only | C++ GraphicsSystem method |
| Terrain mesh API | graphics_bridge.py:361 | Placeholder | Proper mesh generation |

**For Phase 3+**: Complete the above to enable real-time rendering. Headless mode works for all non-graphics testing.
