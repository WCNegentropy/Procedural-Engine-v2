from __future__ import annotations

"""Minimal deterministic engine stub.

This Python implementation mirrors the FFI API surface described in
``AGENTS.md``.  It is intentionally lightweight and suitable only for
unit tests and design exploration.  All submitted buffers are hashed on
enqueue and incorporated into state snapshots so that determinism can be
verified without a full C++ runtime.
"""

from collections import deque
from dataclasses import dataclass, field
from hashlib import sha256
from typing import List, Dict, Any, Iterable, Deque
import json

# Maximum number of descriptor hashes to retain for state snapshots.
# This prevents unbounded memory growth in long-running sessions while
# maintaining enough history for determinism verification.
MAX_DESCRIPTOR_HISTORY = 1024


@dataclass
class _BufferRecord:
    """Record storing the SHA-256 digest of a submitted buffer."""

    name: str
    digest: bytes


@dataclass
class Engine:
    """Reference deterministic engine implemented in Python."""

    _frame: int = 0
    _buffers: List[_BufferRecord] = field(default_factory=list)
    _descriptors: Deque[bytes] = field(
        default_factory=lambda: deque(maxlen=MAX_DESCRIPTOR_HISTORY)
    )
    _hot_reload_hashes: Deque[int] = field(
        default_factory=lambda: deque(maxlen=MAX_DESCRIPTOR_HISTORY)
    )

    def reset(self) -> None:
        """Reset the engine to its initial state.

        The method clears all recorded buffer hashes, descriptor hashes and
        hot-reload requests while also rewinding the internal frame counter to
        zero.  This mirrors reinitialising the runtime and is useful in tests
        that need a pristine deterministic baseline.
        """

        self._frame = 0
        self._buffers.clear()
        self._descriptors.clear()
        self._hot_reload_hashes.clear()

    def enqueue_heightmap(self, h16: memoryview, biome8: memoryview, river1: memoryview) -> None:
        """Accept terrain buffers and store their hashes.

        Parameters
        ----------
        h16, biome8, river1:
            Memory views of the height, biome, and river maps.  These are
            hashed immediately; the original buffers are not retained to
            honor the immutability rule across the FFI boundary.
        """

        for name, buf in ("height", h16), ("biome", biome8), ("river", river1):
            data = bytes(buf)
            digest = sha256(data).digest()
            self._buffers.append(_BufferRecord(name, digest))

    def enqueue_prop_descriptor(
        self, descriptors: Dict[str, Any] | List[Dict[str, Any]]
    ) -> None:
        """Store a deterministic hash of ``descriptors``.

        The descriptors are serialized with sorted keys to ensure a stable
        representation before hashing.

        Parameters
        ----------
        descriptors:
            A single descriptor dict or a list of descriptor dicts.
            Single dicts are normalized to a list internally.
        """
        # Normalize single dict to list for consistent handling
        if isinstance(descriptors, dict):
            descriptors = [descriptors]

        canonical = json.dumps(descriptors, sort_keys=True).encode("utf-8")
        self._descriptors.append(sha256(canonical).digest())

    def hot_reload(self, descriptor_hash: int) -> None:
        """Record a hot-reload request by its hash.

        Parameters
        ----------
        descriptor_hash:
            Deterministic hash of the descriptor to reload.  The value is
            masked to 64 bits and stored so that it affects subsequent state
            snapshots.
        """

        mask = (1 << 64) - 1
        self._hot_reload_hashes.append(descriptor_hash & mask)

    def step(self, dt: float) -> None:
        """Advance the engine by one frame.

        Parameters
        ----------
        dt:
            Time step for the simulation.  The value is not used by this
            stub but is included to match the real API.
        """

        self._frame += 1

    def snapshot_state(self, frame: int) -> bytes:
        """Return a deterministic hash of the current engine state."""

        if frame != self._frame:
            raise ValueError("Snapshot frame does not match current frame")

        h = sha256()
        h.update(frame.to_bytes(8, "little"))
        for record in self._buffers:
            h.update(record.name.encode("utf-8"))
            h.update(record.digest)
        for desc_digest in self._descriptors:
            h.update(desc_digest)
        for reload_hash in self._hot_reload_hashes:
            h.update(reload_hash.to_bytes(8, "little"))
        return h.digest()

    def run_and_snapshot(
        self, frames: Iterable[int], *, dt: float = 1.0 / 60.0
    ) -> Dict[int, bytes]:
        """Return state hashes for the requested ``frames``.

        The engine is stepped forward until each frame is reached and a
        snapshot is captured.  ``frames`` must be provided in non-decreasing
        order relative to the current frame; violating this constraint raises
        ``ValueError``.  The returned dictionary maps frame numbers to their
        corresponding SHA-256 digests.
        """

        hashes: Dict[int, bytes] = {}
        last = self._frame
        for target in frames:
            if target < last:
                raise ValueError("frames must be non-decreasing")
            while self._frame < target:
                self.step(dt)
            hashes[target] = self.snapshot_state(target)
            last = target
        return hashes


__all__ = ["Engine"]
