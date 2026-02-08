"""Python-side GameManager that wraps the C++ GameManager FFI module.

Consolidates chunk scheduling, performance tuning, and resource lifecycle
logic that was previously scattered across GameRunner and ChunkManager.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from procengine.world.chunk import ChunkManager
    from procengine.graphics.graphics_bridge import GraphicsBridge
    import numpy as np


@dataclass
class FrameDirective:
    """Python-side fallback FrameDirective for when C++ is unavailable."""

    max_chunk_loads: int = 1
    lod_bias: float = 0.0
    skip_physics_step: bool = False
    recommended_render_distance: int = 6
    recommended_sim_distance: int = 3
    recommended_erosion_iters: float = 0.0


@dataclass
class ManagerConfig:
    """Configuration for the GameManager."""

    frame_budget_ms: float = 13.0
    terrain_octaves: int = 6
    terrain_macro_points: int = 8
    terrain_erosion_iters: int = 0
    worker_threads: int = 0  # 0 = auto-detect


class GameManagerBridge:
    """Bridges the C++ GameManager to Python game systems."""

    def __init__(self, seed: int, config: Optional[ManagerConfig] = None) -> None:
        self._config = config or ManagerConfig()
        self._cpp_manager: Optional[Any] = None
        self._fallback = False

        try:
            import procengine_cpp as cpp

            self._cpp_manager = cpp.GameManager(seed, self._config.worker_threads)
            self._cpp_manager.set_frame_budget_ms(self._config.frame_budget_ms)
            self._cpp_manager.set_terrain_config(
                self._config.terrain_octaves,
                self._config.terrain_macro_points,
                self._config.terrain_erosion_iters,
                True,  # compute_slope
            )
        except (ImportError, AttributeError):
            self._fallback = True

    @property
    def available(self) -> bool:
        """Return True when the C++ backend is loaded and ready."""
        return not self._fallback and self._cpp_manager is not None

    def sync_frame(
        self,
        dt: float,
        player_x: float,
        player_z: float,
        render_distance: int,
        sim_distance: int,
        chunk_size: int,
    ) -> Any:
        """Call C++ sync_frame and return a directive.

        Returns a C++ FrameDirective when the backend is available, or a
        Python fallback ``FrameDirective`` with safe defaults otherwise.
        """
        if not self.available:
            return FrameDirective()  # no-op defaults
        return self._cpp_manager.sync_frame(
            dt, player_x, player_z, render_distance, sim_distance, chunk_size
        )

    def collect_ready_chunks(self, max_count: int = 16) -> list:
        """Collect finished terrain generation results from C++ workers."""
        if not self.available:
            return []
        return self._cpp_manager.collect_ready_chunks(max_count)

    def get_metrics(self) -> Optional[Any]:
        """Return performance metrics from the C++ backend, or None."""
        if not self.available:
            return None
        return self._cpp_manager.get_metrics()

    def mark_chunk_uploaded(self, x: int, z: int) -> None:
        """Notify C++ that a chunk has been uploaded to the GPU."""
        if not self.available:
            return
        try:
            import procengine_cpp as cpp

            self._cpp_manager.mark_chunk_uploaded(cpp.ChunkCoord(x, z))
        except Exception:
            pass

    def get_chunks_to_unload(
        self, pcx: int, pcz: int, unload_radius: int
    ) -> list:
        """Return a list of ChunkCoord objects that should be unloaded."""
        if not self.available:
            return []
        return self._cpp_manager.get_chunks_to_unload(pcx, pcz, unload_radius)
