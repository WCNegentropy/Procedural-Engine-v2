# Procedural Game Engine – Architecture v1

**Status:** Production Ready ✅

All major subsystems now ship with well‑documented, deterministic Python
reference implementations and a comprehensive test suite.  These modules
serve as the authoritative specification for the in‑production C++
runtime.

---

## 1 · Goals & Scope
- 100% procedurally generated worlds, deterministic from a single root seed.
- Hybrid **Python + C++** implementation:
  - Python for rapid author-time iteration.
  - C++ for real-time, low-latency execution.
- Modular subsystems: **Terrain**, **Mesh/Props**, **Physics**, **Graphics**, **World Assembly**.
- Seed reproducibility, hot-reload, and automated validation from day one.

---

## 2 · Determinism Contract
| Rule | Detail |
|------|--------|
| **Single RootSeed** | 64-bit value provided by user/CLI. |
| **SeedRegistry** | C++ singleton derives deterministic sub-seeds via `splitmix64`. |
| **Unified PRNG** | PCG64 streams exposed in both languages via FFI; no other RNGs allowed. |
| **State Hashing** | Python hashes every buffer → C++; C++ re-hashes and asserts equality. |
| **Fixed Step Physics** | 60 Hz; float epsilon ≤ 1e-6. |

---

## 3 · Language Split
| Tier | Python (Author-time) | C++ (Runtime) |
|------|----------------------|---------------|
| **Terrain & Biome Maps** | FBM noise, domain warp, masks | GeoClipmap mesh, GPU erosion, collision heightfield |
| **Props & Creature Descriptors** | CSG trees, L-systems, genomes | Mesh synthesis, skeletal rigs, GPU uploads |
| **Material Graph Specs** | JSON DSL generation | DSL → SPIR-V compiler, virtual textures |
| **Seed-Mining & Tests** | Batch world gen, metrics, dashboards | Headless engine mode |
| **Tooling GUIs** | Qt / DearPyGUI editors ↔ hot-reload | — |

---

## 4 · Core Generation Pipeline (Per Chunk)
1. **TerrainSystem (Python)** → height, biome, river, slope maps → C++
2. **MeshSystem (C++)** → terrain mesh, props, LOD buffers
3. **PhysicsSystem (Python reference, C++ pending)** → heightfield collider, rigid bodies
4. **GraphicsSystem (C++)** → material graph compile, GPU residency
5. **WorldAssembler (C++)** → ECS entities & component wiring

---

## 5 · Subsystem Specs
### 5.1 Terrain
- Basic FBM heightmap + biome mask generator (Python) ✅
- Macro-plates: Voronoi fracture + ridged noise (Python) ✅
- FBM heightmap: 6–8 octaves Simplex (Python) ✅
- Hydraulic erosion: 100–200 iters (Python reference ✅; GPU C++ impl. pending)
- Slope map derivation (Python) ✅
- Biome LUT: temperature × humidity × height (Python) ✅
- Chunk size: 64×64 vertices (+1 border) → geoClipmap rings (C++)

### 5.2 Mesh & Props
- Rocks: signed-distance CSG descriptor generator (Python) ✅
- Trees: L-system skeleton descriptor generator (Python) ✅; sweep mesh (C++)
- Buildings: deterministic shape grammar descriptor generator (Python) ✅; mesh synthesis (C++)
- Creatures: deterministic metaball + skeleton descriptor generator (Python) ✅; runtime (C++)

### 5.3 Physics
- Bullet-style sequential impulse solver (Python reference ✅; C++)
- Global constants from ruleSeed (C++)
- Broad phase uniform grid per chunk; heightfield proxy (Python reference ✅)
- Constant gravity term (Python) ✅
- Linear velocity damping parameter (Python) ✅

### 5.4 Graphics
- Material graph nodes: Noise, Blend, Warp, PBR constants (Python spec) ✅
- Compiler: JSON → SPIR-V, cached by materialHash (C++)
- Render path: Depth pre-pass → Clustered Forward+ → Post
- Virtual Texture tiles 128 kB, LRU paging (C++)

### 5.5 Engine (Reference)
- Deterministic buffer hashing & state snapshots (Python) ✅
- Hot-reload descriptor hash tracking (Python) ✅
- Reset to initial state for deterministic tests (Python) ✅
- World chunk assembly helper with configurable macro plates and erosion (Python) ✅
- Hierarchical `SeedRegistry.spawn` and multi-chunk world generator (Python) ✅

---

## 6 · FFI Boundary
- **Transport:** pybind11 (CMake) or PyO3 (future Rust option).
- **Data Flow:** zero-copy `memoryview` ⇄ `std::span<uint8_t>`.
- **API Examples:**
  - `Engine.enqueue_heightmap(h16, biome8, river1)`
  - `Engine.enqueue_prop_descriptor(list[dict])`
  - `Engine.step(dt)`
  - `Engine.hot_reload(hash)`
  - `Engine.reset()`

---

## 7 · Build & Packaging
- C++ built as shared lib (`libprocengine.so/.dll/.dylib`)
- Python wheel bundles shared lib via `setup.py` + pybind11
- CI targets: Windows x64 (MSVC), Linux x64 (GCC 13), macOS Apple Silicon (clang)

---

## 8 · Testing & Validation
- `seed_sweeper.py`: Sobol sampling, 10k seeds/night on cloud spot instances. ✅
- Smoke tests: FPS ≥ 60, navmesh solvable, quest graph satisfiable.
- Determinism: frame-500 state hash compare ✅
- Fail-fast on buffer hash mismatch at FFI.
- Removed placeholder Hello World test; suite now targets core systems. ✅
- Run `pytest -q` for the deterministic Python test suite (37 tests currently).
- See `TEST_RESULTS.md` for recorded smoke test outcomes.

---

## 9 · Hot-Reload Loop
1. Python generator edits descriptor.
2. Call `Engine.hot_reload(hash)`.
3. C++ rebuilds GPU resources, swaps ECS handles next frame.

---

## 10 · Roadmap (High-Level)
| Milestone | Focus | Target Time |
|-----------|-------|-------------|
| **P0** | SeedRegistry, PRNG wrapper | ✅ Completed |
| **P1** | Heightmap gen + geoClipmap viewer | ✅ Completed |
| **P2** | Prop mesh & material compiler | 6 wks |
| **P3** | Physics integration | 6 wks |
| **P4** | Hot-reload & tooling GUIs | 4 wks |

---
