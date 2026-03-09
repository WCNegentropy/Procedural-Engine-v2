# Next Steps Plan: Visual Fixes, Creature System, and Prop Polish

**Date:** 2026-03-08 (updated 2026-03-09)
**Scope:** Post-materials-pipeline assessment and implementation roadmap
**Prerequisites:** Passing build, validated materials pipeline, expanded prop families connected, main menu system consolidated

---

## Table of Contents

1. [Issue 1: Washed-Out Lighting](#issue-1-washed-out-lighting)
2. [Issue 2: Tiny Cube Props](#issue-2-tiny-cube-props)
3. [Issue 3: Prop Spawn Height Audit & Fixes](#issue-3-prop-spawn-height-audit--fixes)
4. [Issue 4: Pine Tree Visual Improvement](#issue-4-pine-tree-visual-improvement)
5. [Issue 5: Creature System — Game Loop Integration](#issue-5-creature-system--game-loop-integration)
6. [Issue 6: Materials Pipeline Expansion](#issue-6-materials-pipeline-expansion)
7. [Priority & Sequencing](#priority--sequencing)

---

## Issue 1: Washed-Out Lighting

### Problem Statement

The rendered scene appears pale, desaturated, and greyish-white. Colors are pastel-like across both terrain and props. This was present before the materials pipeline landed but has worsened since, because the new material system changes how light interacts with surfaces.

### Root Cause Analysis

After auditing the full rendering pipeline (`cpp/graphics.cpp`, `cpp/materials.cpp`, `procengine/graphics/graphics_bridge.py`), there are **multiple compounding factors** that together produce the washed-out look:

#### Factor A: Tone Mapping Mismatch Between Terrain and Material Pipelines

The default terrain shader in `cpp/graphics.cpp:2651-2653` has Reinhard tone mapping **explicitly commented out** with the note:

```glsl
// Tone mapping disabled: Reinhard compression makes non-HDR colors look washed out
// (A value of 1.0 gets compressed to 0.5, losing saturation)
```

However, the PBR material pipeline in `cpp/materials.cpp:416-419` **does apply** Reinhard tone mapping:

```glsl
color = color / (color + vec3(1.0));  // HDR tonemapping
color = pow(color, vec3(1.0/2.2));    // Gamma correction
```

This means terrain chunks using biome material pipelines get their colors compressed through Reinhard while surrounding terrain rendered via the default shader does not. The result is visual inconsistency and saturation loss on material-pipeline chunks.

#### Factor B: Excessive Ambient Light Floor

The default fragment shader applies a hard-coded ambient minimum of `vec3(0.15)` (`cpp/graphics.cpp:2638`). This gets **added** on top of an already-bright three-light model:

| Light Source | Color | Multiplier |
|---|---|---|
| Sun | `(1.0, 0.95, 0.85)` | 1.2x diffuse |
| Sky | `(0.4, 0.5, 0.7)` | 0.25x with hemisphere bias (`*0.5 + 0.5`) |
| Ground bounce | `(0.2, 0.15, 0.1)` | 0.3x diffuse |
| Ambient floor | `(0.15, 0.15, 0.15)` | additive constant |

The hemisphere bias on sky light (`skyDiffuse = max(dot(normal, skyDir), 0.0) * 0.5 + 0.5`) means even downward-facing surfaces receive at minimum 50% of sky light contribution. Combined with the ambient floor, there are effectively **no dark areas** in the scene, which kills contrast and makes everything look flat and pale.

#### Factor C: Fog Blending Toward a Bright Color

Exponential fog uses color `vec3(0.4, 0.5, 0.7)` with coefficient `0.0027` and max opacity `0.75`. While the fog distance is relatively far (~370 units for noticeable effect), terrain chunks at medium distance are already being blended toward this sky-blue color, which further desaturates and lightens the scene.

#### Factor D: Material Default Values Favor Matte/Gray Appearance

- `PBRConstNode` defaults to albedo `(0.5, 0.5, 0.5)` (mid-gray)
- Default roughness: high (`1.0 - noise * 0.5`), producing matte surfaces
- Default metallic: `0.0` (non-metallic), minimizing specular highlights
- Fresnel F0 at `vec3(0.04)` (non-metallic baseline) provides little reflective punch

#### Factor E: Biome Vertex Colors Are Naturally Desaturated

The 16 biome colors in `cpp/terrain.cpp:648-665` are realistic/muted rather than vibrant. Combined with the lighting over-brightness, they wash out further.

### Proposed Solution — Multi-Pronged Approach

#### Step 1: Unify Tone Mapping Strategy

**Files:** `cpp/graphics.cpp`, `cpp/materials.cpp`

Either:
- **(Option A — Recommended)** Remove Reinhard from the material pipeline too, since the engine is not producing HDR values. The vertex colors and biome albedos are all in [0, 1] range; tone mapping only compresses them. Keep gamma correction only.
- **(Option B)** Switch both pipelines to an ACES filmic curve (`x * (2.51x + 0.03) / (x * (2.43x + 0.59) + 0.14)`), which handles the [0, 1] range more gracefully than Reinhard and preserves saturation better.

#### Step 2: Reduce Ambient and Sky Light Contribution

**File:** `cpp/graphics.cpp` (default fragment shader)

- Reduce ambient floor from `vec3(0.15)` to `vec3(0.05)` — just enough to prevent total black
- Remove the hemisphere bias on sky light: change `skyDiffuse = max(dot(normal, skyDir), 0.0) * 0.5 + 0.5` to `skyDiffuse = max(dot(normal, skyDir), 0.0)` — surfaces facing away from sky should not receive 50% sky light
- Consider reducing sun multiplier from `1.2` to `1.0` to avoid over-bright highlights
- Reduce sky multiplier from `0.25` to `0.15`

Expected result: deeper shadows, more contrast, colors appear richer because they aren't fighting additive light.

#### Step 3: Darken and Desaturate Fog Color

**File:** `cpp/graphics.cpp` (default fragment shader)

- Change fog color from `vec3(0.4, 0.5, 0.7)` to something less bright, e.g. `vec3(0.3, 0.35, 0.5)` — a deeper atmospheric haze
- Consider reducing fog max opacity from `0.75` to `0.6`, or increasing the distance coefficient slightly so fog only affects truly distant chunks

#### Step 4: Boost Biome Color Saturation

**File:** `cpp/terrain.cpp`

Apply a saturation boost to the biome color palette. This can be done either:
- At the palette level: manually adjust the 16 RGB triplets to be ~20-30% more saturated
- At the shader level: add a saturation multiplier in the fragment shader (more flexible, tunable at runtime)

A shader-level approach is more maintainable:
```glsl
float luminance = dot(albedo, vec3(0.2126, 0.7152, 0.0722));
albedo = mix(vec3(luminance), albedo, 1.3);  // 30% saturation boost
```

#### Step 5: Expose Lighting Parameters as Uniforms

**Files:** `cpp/graphics.cpp`, `cpp/graphics.h`

Currently all lighting values are hard-coded in the shader. Exposing them as uniforms (or push constants) enables runtime tuning without recompilation:
- `uAmbientStrength`
- `uSunIntensity`
- `uSkyIntensity`
- `uFogDensity`
- `uFogColor`
- `uSaturationBoost`

Wire these through `GraphicsBridge` so they can be adjusted via the in-game console command system.

### Testing Strategy

- Visual regression: before/after screenshots at same seed + camera position
- Ensure terrain and material-pipeline chunks look consistent side-by-side
- Test in multiple biomes (forest, desert, mountain, ocean edge) to verify nothing goes too dark
- Verify gamma correction is still applied correctly (check if output looks correct on sRGB display)

### Estimated Scope

This is primarily shader and rendering constant changes. The core change (Steps 1-3) involves modifying a small number of shader string constants in `cpp/graphics.cpp` and `cpp/materials.cpp`. Step 4 is a small shader addition or palette edit. Step 5 (exposing uniforms) is a larger but optional quality-of-life enhancement.

---

## Issue 2: Tiny Cube Props

### Problem Statement

Very small cube-shaped objects are visible in the world, smaller than rock props.

### Root Cause Analysis

The entity mesh upload pipeline in `procengine/graphics/graphics_bridge.py:725-727` has a catch-all fallback for any `entity_type` that doesn't match a known handler:

```python
else:
    # Default small box
    mesh = cpp.generate_box_mesh(cpp.Vec3(0.5, 0.5, 0.5))
```

This produces a 0.5-unit cube for any prop type that reaches the graphics bridge without a matching mesh generator. There are two likely sources:

#### Hypothesis A: Creature Props Failing Mesh Generation

Creatures are spawned in `generate_chunk_props` (15% chance per attempt, 2 attempts per chunk). Their mesh generation in `graphics_bridge.py:700-716` uses marching cubes on metaball implicit surfaces — a computationally expensive path that can fail. When it fails, the fallback is a capsule (`generate_capsule_mesh(0.3, 1.0, 12, 6)`), which would be visually identifiable as a capsule, not a cube. However, if the `entity_state` dict is malformed or missing keys, it may fall through to the `else` branch and produce the 0.5-unit box.

#### Hypothesis B: Building Props With Default 1.0-Unit Size

`generate_building_descriptors` uses a default `size=1.0`, meaning root blocks start at 1x1x1 units. After 1-3 BSP splits, individual leaf blocks can be as small as 0.3x1.0x0.3 units. The building mesh path exists in `graphics_bridge.py:717-724` but buildings are **not spawned** by `generate_chunk_props` — they are only generated through the static `world.py` path. If buildings somehow enter the chunk pipeline (e.g., from a legacy codepath or from an older save), they'd render correctly through their handler but at a very small default size.

#### Hypothesis C: Unknown Prop Type String Mismatch

If any prop descriptor has a `type` field that doesn't match the if/elif chain in `_spawn_chunk_props` (e.g., a typo or a future prop type name), it falls through to the generic `Prop` fallback at `game_runner.py:2127-2138`, which spawns it with `prop_type=prop_type` and `state=prop_desc.get("state", {})`. When this reaches `upload_entity_mesh`, the type won't match any known handler and hits the 0.5-unit box fallback.

### Proposed Solution

#### Step 1: Add Diagnostic Logging

**File:** `procengine/graphics/graphics_bridge.py`

Add a warning log in the `else` fallback branch (line 725-727) that prints the unknown `entity_type` and `entity_state`:

```python
else:
    logger.warning(f"Unknown entity type '{entity_type}' — generating default box. "
                   f"State keys: {list((entity_state or {}).keys())}")
    mesh = cpp.generate_box_mesh(cpp.Vec3(0.5, 0.5, 0.5))
```

This will immediately reveal what's hitting the fallback path when running the game.

#### Step 2: Investigate and Fix the Source

Once the diagnostic log identifies the prop type(s) producing the cubes:
- If it's a type string mismatch: fix the string or add a handler
- If it's creature mesh failures: improve the metaball descriptor validation or make the capsule fallback more robust
- If it's buildings: either add building spawning to `generate_chunk_props` with proper sizing (see below), or ensure buildings don't accidentally enter the chunk pipeline

#### Step 3: Improve Fallback Mesh Visibility

Replace the tiny 0.5-unit box fallback with something more obviously diagnostic — e.g., a bright magenta 1.0-unit box — so unknown prop types are immediately identifiable during development rather than being easy to confuse with intended content.

### Estimated Scope

Step 1 is a 1-line logging change. Steps 2-3 depend on what the log reveals, but are likely small fixes.

---

## Issue 3: Prop Spawn Height Audit & Fixes

### Problem Statement

At least one prop type (likely flower_patch or dead_tree, described as "small sticks sticking out of the ground") spawns below the terrain surface, appearing cut off. All prop spawn heights should be audited for correctness.

### Current Y-Offset Map

From `procengine/game/game_runner.py:1992-2138`:

| Prop Type | Y-Position | Y-Offset | Mesh Origin Point | Expected Result |
|---|---|---|---|---|
| rock | `global_y + 0.1` | +0.1 | Center of sphere | Correct (half above, half below terrain with slight lift) |
| tree | `global_y` | 0.0 | Base of trunk (L-system starts at origin, grows upward) | Correct |
| bush | `global_y + 0.1` | +0.1 | Center of squashed sphere (Y shifted up internally by `radius * 0.55 * 0.5`) | Correct |
| pine_tree | `global_y` | 0.0 | Base of trunk (cylinder shifted up by `trunk_height * 0.5` internally) | Correct |
| dead_tree | `global_y` | 0.0 | Base of trunk (L-system starts at origin) | Correct |
| fallen_log | `global_y + 0.1` | +0.1 | Center of cylinder (rotated horizontal, lifted by `radius` internally) | Correct |
| boulder_cluster | `global_y + 0.1` | +0.1 | Center of first rock | Correct |
| flower_patch | `global_y` | 0.0 | Depends on mesh generation | **Needs investigation** |
| mushroom | `global_y` | 0.0 | Base of stem (cylinder shifted up by `stem_height * 0.5` internally) | Correct |
| cactus | `global_y` | 0.0 | Base of column (cylinder shifted up by `main_height * 0.5` internally) | Correct |
| creature | `global_y` | 0.0 | Marching cubes grid origin | **May clip** |

### Likely Culprit: Flower Patch

The flower patch mesh generator (`cpp/props.cpp:868-916`) creates thin vertical stems with small bud spheres. The stems are `0.3` units tall with radius `0.015` units — visually they look like small sticks. Key question: **does the mesh generator position stems above the descriptor's position.y, or centered on it?**

From the code, the stem cylinder is generated via `generate_cylinder_mesh(stem_radius, stem_height, stem_segments)` which centers the cylinder on the origin, then shifts it. If the shift only moves it up by `stem_height * 0.5`, the bottom half of each stem sits below the spawn point. With `global_y` having no offset, the bottom portion would be below terrain.

### Proposed Solution

#### Step 1: Audit Flower Patch Mesh Origin

**File:** `cpp/props.cpp` (flower patch section, ~lines 868-916)

Verify that each stem cylinder's base sits at or above `position.y`. If the cylinder is centered (base at `-stem_height/2`), the stems will sink below terrain. Fix by shifting each stem up by `stem_height * 0.5` so the base sits at the descriptor position.

#### Step 2: Add Small Y-Offset for Flower Patch Spawning

**File:** `procengine/game/game_runner.py`

Add a small positive Y-offset to flower_patch spawning (similar to `ROCK_Y_OFFSET`):

```python
elif prop_type == "flower_patch":
    prop = Prop(
        entity_id=entity_id,
        position=Vec3(global_x, global_y + 0.05, global_z),  # Slight lift
        ...
    )
```

A `0.05` offset is enough to prevent clipping without making them visually float.

#### Step 3: Creature Y-Offset

Creatures also spawn with no Y-offset. The marching cubes mesh grid origin is at the descriptor position, but the metaball centers are generated as `rng.random(3)` — values in [0, 1]. This means the creature mesh likely extends both above and below the spawn point. Add a Y-offset or shift the marching cubes grid so the creature's base sits on the terrain.

#### Step 4: Create a Standard Y-Offset Constant Map

Rather than scattering per-type offsets through the if/elif chain, create a clear constant map:

```python
PROP_Y_OFFSETS = {
    "rock": 0.1,
    "bush": 0.1,
    "fallen_log": 0.1,
    "boulder_cluster": 0.1,
    "flower_patch": 0.05,
    "mushroom": 0.0,
    "creature": 0.15,
    # tree types with 0.0 offset have meshes that already start at base
}
```

This makes the offset logic explicit and easy to audit/tune.

### Estimated Scope

Small changes to `game_runner.py` (Y-offsets) and possibly `cpp/props.cpp` (mesh origin fix for flower patch). The constant map refactor is optional but improves maintainability.

---

## Issue 4: Pine Tree Visual Improvement

### Problem Statement

The pine tree prop achieves the general conifer silhouette but looks blocky and artificial — more like a low-poly Roblox tree than the natural-looking organic style seen in other props (rocks, bushes, etc.). The stacked perfect-cone geometry is too regular and uniform.

### Current Pine Tree Mesh

From `cpp/props.cpp:736-770`:

- **Trunk:** `generate_cylinder_mesh(trunk_radius, trunk_height, 8 segments)` — a smooth-sided cylinder
- **Canopy:** 2-5 stacked cones via `generate_cone_mesh()`, each with:
  - Linear taper: `cone_radius = canopy_radius * (1.0 - t * 0.6)` (uniform 40% reduction top to bottom)
  - Linear height variation: `cone_height = layer_height * (1.2 - t * 0.3)`
  - Uniform vertical spacing: `y_offset = base_y + layer * layer_height * 0.75`

The problem is that every cone is a **perfect geometric primitive** with no irregularity — the silhouette is a stack of clean triangles.

### Proposed Solution — Two-Pronged Approach

#### Prong 1: Tweak Cone Geometry for More Natural Proportions

**File:** `cpp/props.cpp` (pine tree mesh section)

Current cones look too uniform because:
1. The taper factor `(1.0 - t * 0.6)` produces a near-linear size progression
2. All cones have the same number of segments
3. Layer spacing is too uniform

Proposed changes:
- Use a **concave taper curve** instead of linear: `cone_radius = canopy_radius * pow(1.0 - t, 0.7)` — the bottom layers will be proportionally wider with more dramatic narrowing toward the top, creating a natural conifer silhouette
- Make the **bottom-most cone wider** with a larger base multiplier (e.g., 1.2x canopy_radius) to create the characteristic broad-based conifer shape
- Add **slight cone overlap** — currently cones stack with 0.75x spacing; increase to 0.85x so layers partially overlap, hiding the seams between cones and creating a denser canopy appearance
- Vary **cone height per layer** more dramatically: bottom cones should be flatter/wider, top cones taller/narrower
- Add a **pointed tip cone** at the very top: a narrow, tall cone that gives the classic conifer apex

Example revised parameters:
```
Layer 0 (bottom): radius = canopy_radius * 1.15, height = layer_height * 0.8 (wide, flat)
Layer 1:          radius = canopy_radius * 0.85, height = layer_height * 1.0
Layer 2:          radius = canopy_radius * 0.60, height = layer_height * 1.1
Layer 3 (top):    radius = canopy_radius * 0.35, height = layer_height * 1.3 (narrow, tall)
Apex cone:        radius = canopy_radius * 0.15, height = layer_height * 0.6
```

#### Prong 2: Apply Procedural Noise Mask to Final Mesh

**File:** `cpp/props.cpp`

After generating the stacked-cone canopy mesh, apply a procedural displacement mask to the canopy vertices — similar to how rock meshes use spatially coherent noise to break up the perfect sphere.

Implementation approach:
1. After all canopy cone vertices are generated, iterate over each vertex
2. Compute a noise value based on the vertex's spherical coordinates relative to the tree center (similar to `sphere_noise` used for rocks, but on the canopy envelope)
3. Displace each vertex radially (inward/outward from the trunk center axis) by `noise_value * displacement_scale`
4. Use a coarse noise grid (e.g., 6 rings x 10 segments) with smoothstep interpolation for organic variation
5. Apply a **second octave** at higher frequency with lower amplitude for fine detail
6. Recompute normals from displaced geometry

Parameters to expose in `PineTreeDescriptor`:
- `noise_scale`: magnitude of displacement (e.g., `0.12` = 12% of cone radius)
- `noise_seed`: deterministic per-tree variation (derive from existing descriptor fields via hash)

Expected result: each pine tree has unique, slightly irregular canopy edges that break the perfect-cone silhouette, matching the organic quality of rock and bush meshes. The tree should still read as a conifer from a distance but up close has natural asymmetry and variation.

### Reference: How Rock Noise Works (to replicate for pine trees)

From `cpp/props.cpp:62-145` (rock mesh):
- Coarse noise grid: 5 rings x 7 segments
- Fine noise grid: 10 rings x 14 segments (30% blend)
- `noise_hash()` function: XOR-based Murmur-like scrambling
- `sphere_noise()`: bilinear interpolation over the coarse grid with `smoothstep` blending
- Displacement: `displaced_radius = radius + (noise * 2.0 - 1.0) * noise_magnitude`
- Normals: recomputed from displaced geometry via face-normal accumulation

For pine trees, adapt this to work in **cylindrical coordinates** (angle around trunk + height) rather than spherical, since the canopy is roughly conical rather than spherical.

### Estimated Scope

Moderate C++ work in `cpp/props.cpp`. Prong 1 (geometry tweaks) is straightforward constant/formula changes. Prong 2 (noise displacement) requires implementing a cylindrical noise function and post-processing the canopy vertices, estimated at 50-80 lines of new C++ code modeled on the existing rock noise system.

---

## Issue 5: Creature System — Game Loop Integration

### Current State

The creature skeleton + metaball system is **implemented end-to-end** through the FFI:

- **Descriptors:** `procengine/world/props.py:186-225` generates skeleton (3-6 bones) and metaball (3-7 balls) descriptors
- **Chunk spawning:** `procengine/world/props.py:883-919` places creatures in `generate_chunk_props` (2 attempts/chunk, 15% chance, excluded from BARREN_BIOMES)
- **Game runner spawn:** `procengine/game/game_runner.py:2117-2126` creates `Prop` entities with creature state
- **Mesh generation:** `procengine/graphics/graphics_bridge.py:700-716` routes to `cpp.generate_creature_mesh()` (marching cubes on metaball field) with capsule fallback
- **C++ mesh generator:** `cpp/props.cpp:503-654` implements marching cubes at 32^3 resolution

**However**, creatures are spawned as **static `Prop` entities** — they are placed in the world and rendered, but they do not move, have no AI, have no physics bodies, and have no behavior. They are functionally statues.

### Roadmap to Living Creatures

#### Phase 1: Validate and Stabilize Current Creature Spawning

Before adding movement, ensure the existing spawn + render path works reliably:

1. **Verify creatures actually spawn visually** — run the game and confirm creature meshes render (vs. hitting the box fallback). Add the diagnostic logging from Issue 2 to confirm.
2. **Fix Y-offset** (from Issue 3) so creatures sit on terrain, not clip through it.
3. **Validate metaball descriptor quality** — the current generator uses `rng.random(3)` for metaball centers, placing them randomly in a [0,1] unit cube. This may produce disconnected blobs rather than coherent creature shapes. Consider constraining metaballs to follow the skeleton chain for more anatomically plausible shapes.

#### Phase 2: Promote Creatures from Prop to Character Entity

**Files:** `procengine/game/game_api.py`, `procengine/game/game_runner.py`

Currently creatures use the `Prop` entity class. To enable movement and AI, they need to be `Character` subclasses (or a new `Creature` class extending `Character`):

1. Create a `Creature` class (subclass of `Character`) in `game_api.py`:
   - Inherits `position`, `velocity`, `health` from `Character`
   - Adds `skeleton`, `metaballs` state for mesh generation
   - Adds `species` or `creature_type` for behavioral differentiation
   - Has a `RigidBody3D` for physics

2. Update `_spawn_chunk_props` to spawn `Creature` entities instead of `Prop` when `prop_type == "creature"`

3. Register creatures in `GameWorld` entity tracking so they participate in the existing sim-distance filtering (`get_entities_in_sim_range()`)

#### Phase 3: Basic Movement Without Animation

**Files:** `procengine/game/game_runner.py`, `procengine/game/behavior_tree.py`, `procengine/physics/collision.py`

Give creatures the ability to move around using the existing systems:

1. **Physics body:** Create a `RigidBody3D` for each creature, register it with the physics step. The creature's radius can be derived from the metaball bounding sphere. The existing `step_physics_3d` handles gravity + terrain collision via `HeightField2D` / `ChunkedHeightField`.

2. **Simple behavior tree:** Use the existing `create_patrol_behavior()` or create a `create_wander_behavior()`:
   - Pick a random nearby point within a radius
   - Walk toward it at a slow speed
   - Wait for a few seconds
   - Pick a new point
   - Repeat

   The behavior tree system already handles NPC updates filtered by sim-distance, so creatures would automatically only be simulated when near the player.

3. **Movement execution:** Each frame, the behavior tree sets a target velocity on the creature. The physics step applies gravity and terrain collision. The creature's position updates accordingly. No animation is needed — the mesh simply translates across the terrain (slides along the ground).

4. **Orientation:** Rotate the creature to face its movement direction by updating `entity.rotation` (Y-axis rotation) based on velocity vector: `rotation_y = atan2(velocity.x, velocity.z)`.

#### Phase 4: Deterministic Creature Spawning

Creature placement should be deterministic like all other props:

1. **Per-chunk creature seed:** Use `registry.get_rng("chunk_creatures")` or derive from the chunk coordinate seed. This is already handled by `generate_chunk_props` using `registry.get_rng("chunk_props")`.

2. **Creature type/species system:** Different biomes should produce different creature types:
   - Forest: deer-like (horizontal body, 4 legs)
   - Desert: lizard-like (low body, splayed legs)
   - Mountain: goat-like (compact body, sturdy legs)
   - Plains: herd animals (medium body, long legs)

   Constrain the skeleton and metaball parameters per species template to produce recognizable silhouettes rather than random blobs.

3. **Spawn density by biome:** Currently hardcoded at 2 attempts with 15% chance. Make this biome-dependent:
   - Plains/Forest: 3-4 attempts, 20% chance (more wildlife)
   - Desert/Tundra: 1 attempt, 10% chance (sparse wildlife)
   - Mountain: 2 attempts, 15% chance (moderate)

#### Phase 5: Future — Animation System (Out of Scope for Now)

This is explicitly deferred. The skeleton data is already present in creature descriptors. A future animation system could:
- Define walk cycles as bone angle keyframes
- Interpolate bone transforms per frame
- Regenerate or deform the metaball mesh per frame (expensive) OR use skeletal mesh deformation (requires a different mesh pipeline)

For now, creatures will translate across terrain as rigid bodies. This is sufficient to validate the creature system and create a sense of a living world.

### Estimated Scope

- Phase 1: Small (diagnostic + Y-offset fix)
- Phase 2: Medium (new entity class, spawn logic changes)
- Phase 3: Medium (behavior tree + physics integration, following existing NPC patterns)
- Phase 4: Medium (species templates, biome-dependent spawning)
- Phase 5: Large (deferred, not part of this plan)

---

## Issue 6: Materials Pipeline Expansion

### Current State

The materials pipeline is **validated and connected** for terrain rendering:

- Python generates deterministic biome material graphs (`procengine/world/materials.py`)
- C++ compiles them to GLSL/SPIR-V (`cpp/materials.cpp`)
- `GraphicsBridge` creates and selects GPU pipelines per terrain chunk (`procengine/graphics/graphics_bridge.py:871-903`)
- The result: terrain surfaces now have PBR properties (albedo, roughness, metallic, AO) instead of flat vertex colors

**However**, as noted in the remediation report: "entity rendering still relies on the default pipeline and per-mesh colors rather than per-entity material graphs." Props still use `set_uniform_color()` for flat coloring.

### What the Materials Pipeline Enables (Vision)

The validated pipeline means we can now give any mesh unique physical surface properties:

| Material Type | Roughness | Metallic | Visual Effect |
|---|---|---|---|
| Wet rock | 0.2 | 0.0 | Glossy, reflective surface |
| Dry rock | 0.8 | 0.0 | Matte, rough surface |
| Bark | 0.9 | 0.0 | Very rough, no reflection |
| Leaves | 0.5 | 0.0 | Semi-glossy, waxy coating |
| Crystal | 0.1 | 0.3 | Very glossy, semi-metallic reflection |
| Metal ore | 0.4 | 0.8 | Metallic luster |
| Water surface | 0.05 | 0.0 | Near-mirror reflective |
| Ice | 0.15 | 0.0 | Glossy, translucent feel |
| Sand | 0.95 | 0.0 | Very matte, powdery |
| Mushroom cap | 0.3 | 0.0 | Smooth, slightly glossy |

### Expansion Roadmap

#### Step 1: Fix the Lighting First (Issue 1)

The materials pipeline's PBR calculations depend on having a correct lighting model. Fixing the tone mapping mismatch and ambient over-brightness (Issue 1) is a prerequisite for materials to look right. If lighting is washed out, even perfectly configured PBR materials will look flat.

#### Step 2: Per-Prop-Type Material Graphs

**Files:** `procengine/world/materials.py`, `procengine/game/game_runner.py`, `procengine/graphics/graphics_bridge.py`

Create material graph templates for each prop family:

1. Define material parameters per prop type (roughness, metallic, base albedo adjustment)
2. Generate a material graph per prop type (not per individual prop — that would be too many pipelines)
3. Compile and register these pipelines at startup alongside the biome pipelines
4. Select the appropriate pipeline when drawing each entity

This is the same flow as biome materials but applied to entities instead of terrain.

#### Step 3: Biome-Variant Materials

Extend the per-prop materials to vary by biome:
- Rocks in desert biomes: sandy roughness, warm albedo tint
- Rocks in glacier biomes: icy glossy surface
- Trees in swamp biomes: wet bark (lower roughness)
- Trees in taiga biomes: frost-covered (higher albedo, lower roughness)

This creates visual coherence between terrain materials and prop materials within each biome.

#### Step 4: Exotic Material Types (Future)

Once the basic per-prop pipeline is working:
- **Crystalline materials:** Low roughness, moderate metallic, refractive appearance (via normal perturbation)
- **Emissive materials:** Add emissive term to PBR output for glowing mushrooms, lava rocks, etc.
- **Translucent materials:** Subsurface scattering approximation for leaves, thin mushroom caps
- **Weathering:** Noise-driven roughness variation across a single mesh (e.g., moss on one side of a rock)

### Estimated Scope

Step 1: covered by Issue 1. Step 2: medium (follows established pattern). Step 3: small extension of Step 2. Step 4: large, future work.

---

## Priority & Sequencing

### Recommended Implementation Order

```
Priority 1 (Visual Quality — Immediate Impact)
├── Issue 1: Washed-Out Lighting (Steps 1-4)
│   └── Unblock: Materials pipeline visual quality
│   └── Unblock: All other visual work looks correct
├── Issue 2: Tiny Cube Props (Step 1 — diagnostic logging)
│   └── Quick win, reveals root cause
└── Issue 3: Prop Spawn Height Fixes
    └── Quick win, flower_patch + creature Y-offsets

Priority 2 (Prop Polish — Medium Effort)
├── Issue 2: Tiny Cube Props (Steps 2-3 — fix based on diagnostics)
├── Issue 4: Pine Tree Visual Improvement
│   ├── Prong 1: Cone geometry tweaks
│   └── Prong 2: Procedural noise mask
└── Issue 3: Y-Offset constant map refactor

Priority 3 (Creature System — Larger Effort)
├── Issue 5 Phase 1: Validate creature spawn + render
├── Issue 5 Phase 2: Creature entity class
├── Issue 5 Phase 3: Basic movement + behavior tree
└── Issue 5 Phase 4: Species templates + biome-dependent spawning

Priority 4 (Materials Expansion — Builds on Everything Above)
├── Issue 6 Step 2: Per-prop material graphs
├── Issue 6 Step 3: Biome-variant materials
└── Issue 6 Step 4: Exotic material types (future)
```

### Dependency Graph

```
Issue 1 (Lighting Fix)
    │
    ├──→ Issue 4 (Pine Tree) — needs correct lighting to evaluate visual results
    ├──→ Issue 6 (Materials Expansion) — needs unified tone mapping
    └──→ Issue 5 Phase 1 (Creature Validation) — needs correct lighting to see creatures

Issue 2 (Tiny Cubes) — independent, can be done in parallel with Issue 1
    │
    └──→ Issue 5 Phase 1 — cubes may be creature fallbacks

Issue 3 (Spawn Heights) — independent, can be done in parallel with Issue 1
    │
    └──→ Issue 5 Phase 1 — creature Y-offset needed

Issue 5 Phase 2-4 (Creature Movement)
    │
    └──→ Issue 6 Step 2 — creature materials

Issue 4 (Pine Tree)
    │
    └──→ Issue 6 Step 2 — pine tree material graphs
```

### What Can Be Parallelized

These work items have no dependencies on each other and can be done simultaneously:
- Issue 1 (lighting fix) + Issue 2 Step 1 (diagnostic logging) + Issue 3 (spawn heights)
- Issue 4 Prong 1 (cone geometry) + Issue 5 Phase 1 (creature validation)

### Files Touched Per Issue

| Issue | Primary Files |
|---|---|
| 1 — Lighting | `cpp/graphics.cpp`, `cpp/materials.cpp`, `cpp/terrain.cpp` |
| 2 — Tiny Cubes | `procengine/graphics/graphics_bridge.py` |
| 3 — Spawn Heights | `procengine/game/game_runner.py`, possibly `cpp/props.cpp` |
| 4 — Pine Tree | `cpp/props.cpp`, `cpp/props.h` |
| 5 — Creatures | `procengine/game/game_api.py`, `procengine/game/game_runner.py`, `procengine/game/behavior_tree.py`, `procengine/world/props.py` |
| 6 — Materials | `procengine/world/materials.py`, `procengine/graphics/graphics_bridge.py`, `procengine/game/game_runner.py` |

---

## Appendix: Key Code Locations Reference

> **Note:** Line numbers below were captured before the main menu consolidation
> (2026-03-09) which added ~300 lines to `game_runner.py` and ~380 lines to
> `ui_system.py`. Offsets in those files may have shifted; use symbol search
> rather than absolute line numbers.

| System | File | Lines | Description |
|---|---|---|---|
| Default terrain shader | `cpp/graphics.cpp` | 2616-2659 | Lighting, fog, tone mapping, gamma |
| PBR material shader | `cpp/materials.cpp` | 361-428 | Material fragment shader template |
| PBR lighting functions | `cpp/materials.cpp` | 189-261 | Fresnel, GGX, Smith geometry |
| Biome color palette | `cpp/terrain.cpp` | 648-665 | 16 biome RGB values |
| Material graph DSL | `procengine/world/materials.py` | 19-59 | `generate_material_graph()` |
| Material pipeline creation | `procengine/graphics/graphics_bridge.py` | 871-903 | `create_material_pipeline()` |
| Biome pipeline selection | `procengine/game/game_runner.py` | 1425-1473 | Per-chunk pipeline select |
| Entity mesh upload | `procengine/graphics/graphics_bridge.py` | 570-775 | All prop mesh handlers |
| Entity color map | `procengine/graphics/graphics_bridge.py` | 148-164 | `ENTITY_COLORS` dict |
| Prop spawn logic | `procengine/game/game_runner.py` | 1976-2145 | `_spawn_chunk_props()` |
| Prop render scale | `procengine/game/game_runner.py` | 76-90 | `_prop_render_scale()` |
| Chunk prop generation | `procengine/world/props.py` | 507-919 | `generate_chunk_props()` |
| Rock mesh (noise reference) | `cpp/props.cpp` | 62-145 | Spatially coherent noise on sphere |
| Pine tree mesh | `cpp/props.cpp` | 736-770 | Cylinder trunk + stacked cones |
| Flower patch mesh | `cpp/props.cpp` | 868-916 | Stems + bud spheres |
| Creature mesh (marching cubes) | `cpp/props.cpp` | 503-654 | Metaball implicit surface |
| Creature descriptor gen | `procengine/world/props.py` | 186-225 | Skeleton + metaball params |
| Behavior tree factory | `procengine/game/behavior_tree.py` | `create_patrol_behavior()` | Reusable for creatures |
| Sim-distance filtering | `procengine/game/game_api.py` | `get_entities_in_sim_range()` | Entity update filtering |
