# CLAUDE.md — Claude Code Configuration

This file configures Claude Code for optimal assistance with the Procedural Engine v2 and related projects in this development environment.

---

## Project Overview

**Procedural Engine v2** is a hybrid Python/C++ procedural game engine with:
- 100% deterministic world generation from a single 64-bit seed
- Vulkan-based rendering with virtual texture paging
- 3D physics with hybrid 2D+height approach
- Hot-reload infrastructure for iterative development

**Current Status:** Production Ready (v1.1) — Active development toward v2.0 AI-native RPG platform.

---

## MCP Servers Available

The following MCP servers are configured in `.vscode/mcp.json` and available for enhanced capabilities:

### GitHub MCP (`github-mcp`)
- **Purpose:** Direct GitHub platform integration
- **Capabilities:** Repository browsing, issue/PR management, code search, workflow analysis
- **Auth:** Uses `GITHUB_TOKEN` environment variable (already configured)
- **Use for:** Creating issues, reviewing PRs, searching code across repos, automating GitHub workflows

### Memory Server (`@modelcontextprotocol/server-memory`)
- **Purpose:** Persistent knowledge graph across sessions
- **Capabilities:** Store entities, relationships, and observations
- **Use for:** Remembering architectural decisions, tracking ongoing work, maintaining context about the engine's subsystems

### Sequential Thinking (`@modelcontextprotocol/server-sequential-thinking`)
- **Purpose:** Step-by-step reasoning for complex problems
- **Capabilities:** Structured problem decomposition, thought logging
- **Use for:** Debugging physics solver issues, planning architectural changes, working through algorithmic challenges

### Filesystem Server (`@modelcontextprotocol/server-filesystem`)
- **Purpose:** Secure file operations within project scope
- **Scope:** `/workspaces/Procedural-Engine-v2`
- **Use for:** Batch file operations, safe automated file management

---

## Development Environment

### Runtime Versions
- **Python:** 3.10+ (3.12 in this codespace)
- **Node.js:** 24.x with npm 11.x
- **C++:** C++17 standard
- **CMake:** 3.14+

### Key Paths
```
/workspaces/Procedural-Engine-v2/     # Project root
├── cpp/                              # C++ source (pybind11 module)
├── build/                            # CMake output
├── .vscode/mcp.json                  # MCP server configuration
└── procengine_cpp.*.so               # Compiled Python extension
```

### Build Commands
```bash
# Headless build (no Vulkan required)
cd cpp && mkdir -p build && cd build
cmake .. -DNO_GRAPHICS=ON && make

# Full build with graphics
cmake .. && make

# Run tests (172+ tests)
python -m pytest -q

# Lint and format
ruff check . && ruff format .

# Type check
mypy .
```

---

## Architecture Quick Reference

### Hybrid Python/C++ Design
```
Python (Author-time)              C++ (Runtime)
────────────────────              ─────────────
Terrain descriptors      FFI→     GeoClipmap mesh, GPU erosion
Prop descriptors         FFI→     Mesh synthesis, skeletal rigs
Material graph specs     FFI→     SPIR-V compiler, virtual textures
Physics reference impl   FFI→     Physics simulation
Hot-reload control       FFI→     Resource rebuild queue
```

### Core Modules

| Module | Purpose | Key Classes/Functions |
|--------|---------|----------------------|
| `engine.py` | Core engine, state snapshots | `Engine`, `snapshot_state()`, `hot_reload()` |
| `physics.py` | 2D/3D physics simulation | `Vec3`, `RigidBody3D`, `HeightField2D`, `step_physics_3d()` |
| `terrain.py` | Procedural terrain generation | `terrain_chunk()`, FBM noise, erosion, biomes |
| `props.py` | Procedural prop generation | Rocks, trees, buildings, creatures |
| `materials.py` | Material graph DSL | Node-based material specifications |
| `world.py` | Multi-chunk world assembly | `generate_chunk()`, `generate_world()` |
| `seed_registry.py` | Deterministic PRNG | `SeedRegistry`, PCG64, splitmix64 |

---

## Coding Standards

### Python Style
- **Line length:** 100 characters (ruff enforced)
- **Quotes:** Double quotes
- **Type hints:** Required on all public functions
- **Docstrings:** NumPy format with Parameters, Returns, Examples
- **Imports:** Sorted via isort (ruff I)

### Naming Conventions
```python
# Classes: PascalCase
class RigidBody3D:
    pass

# Functions/methods: snake_case
def step_physics_3d(bodies, dt, gravity):
    pass

# Private module vars: _prefixed
_MASK64 = 0xFFFFFFFFFFFFFFFF

# Constants: UPPER_CASE
MAX_DESCRIPTOR_HISTORY = 1024
DEFAULT_DT = 1.0 / 60.0
```

### C++ Style
- **Standard:** C++17
- **Naming:** PascalCase classes, snake_case methods, trailing `_` for members
- **Headers:** `#pragma once`, inline implementations for performance

---

## Determinism Contract

This is the most critical constraint of the engine. All output must be reproducible from seeds.

| Rule | Implementation |
|------|----------------|
| Single RootSeed | 64-bit value provided by user |
| SeedRegistry | Deterministic sub-seeds via splitmix64 |
| Unified PRNG | PCG64 streams in both Python and C++ |
| State Hashing | SHA-256 verification at FFI boundary |
| Fixed Timestep | 60 Hz physics (dt = 1/60) |

**Never:**
- Use `random` module directly (always use SeedRegistry)
- Allow floating-point non-determinism before hashing
- Mutate buffers after FFI hand-off

---

## Testing Patterns

### Test Organization
```
test_*.py           # 18 test files, 172+ tests
├── test_engine.py          # Core engine tests
├── test_physics.py         # 2D physics (18 tests)
├── test_physics_3d.py      # 3D physics (49 tests)
├── test_terrain.py         # Terrain generation
├── test_cpp_*.py           # C++ integration tests
└── conftest.py             # Pytest configuration
```

### Running Tests
```bash
# All tests
python -m pytest -q

# Specific module
python -m pytest test_physics_3d.py -v

# Skip C++ graphics tests (headless)
python -m pytest --ignore=test_cpp_graphics.py
```

### Determinism Testing Pattern
```python
def test_same_seed_same_output():
    registry_a = SeedRegistry(42)
    registry_b = SeedRegistry(42)
    # Same seeds must produce identical results
    assert registry_a.get_subseed("terrain") == registry_b.get_subseed("terrain")
```

---

## Common Tasks

### Adding a New Python Module
1. Create `module_name.py` in project root
2. Add to `py-modules` in `pyproject.toml`
3. Add to `known-first-party` in ruff config
4. Create `test_module_name.py` with tests
5. Run `ruff check . && python -m pytest`

### Adding C++ Functionality
1. Add `.cpp/.h` files to `cpp/`
2. Update `CMakeLists.txt` source list
3. Add pybind11 bindings in `engine.cpp`
4. Create matching Python tests in `test_cpp_*.py`
5. Build and test: `cd cpp/build && make && cd ../.. && python -m pytest`

### Debugging Physics Issues
1. Use sequential-thinking MCP for step-by-step analysis
2. Check determinism: same inputs must produce same outputs
3. Verify dt = 1/60 fixed timestep
4. Check heightfield bounds and interpolation
5. Run `test_physics_3d.py` for regression

### Working with Seeds
```python
from seed_registry import SeedRegistry

# Create registry with root seed
registry = SeedRegistry(42)

# Get deterministic sub-seeds
terrain_seed = registry.get_subseed("terrain")
props_seed = registry.get_subseed("props")

# Get numpy RNG for random operations
rng = registry.get_rng("creature_gen")
values = rng.integers(0, 100, size=10)
```

---

## CI/CD Pipeline

GitHub Actions workflow (`.github/workflows/ci.yml`):

1. **Lint Job:** ruff check, mypy (advisory)
2. **Python Tests:** Pure Python tests (no C++)
3. **Linux Build:** Full CMake with Vulkan, all tests
4. **Windows Build:** MSVC, Vulkan SDK, integration tests
5. **macOS Build:** MoltenVK, Homebrew deps, integration tests

### Before Committing
```bash
ruff check . && ruff format --check .
python -m pytest -q
# Update TEST_RESULTS.md if tests changed
```

---

## Key Files Reference

| File | Purpose |
|------|---------|
| `AGENTS.md` | Determinism contract, architecture rules |
| `README.md` | User-facing documentation |
| `plan.md` | Development roadmap (Phase 1-4) |
| `pyproject.toml` | Python package config, tool settings |
| `setup.py` | CMake extension builder |
| `cpp/CMakeLists.txt` | C++ build configuration |
| `.github/workflows/ci.yml` | CI/CD pipeline |

---

## Project-Specific Reminders

1. **Determinism is paramount** — Every random operation must flow through SeedRegistry
2. **Python = author-time, C++ = runtime** — No per-frame Python in gameplay
3. **Test before commit** — All 172+ tests must pass
4. **Update TEST_RESULTS.md** — After meaningful test changes
5. **Immutable after FFI** — Never mutate buffers post-handoff
6. **Fixed timestep** — Physics always at 60 Hz (dt = 1/60)

---

## Future Work (Phase 2-4)

- **Phase 2:** Game loop, NPC framework, UI (Dear ImGui)
- **Phase 3:** MCP server for AI-powered NPCs, Game Master mode
- **Phase 4:** Command architecture, console, keybinds, modding

See [plan.md](plan.md) for complete roadmap.
