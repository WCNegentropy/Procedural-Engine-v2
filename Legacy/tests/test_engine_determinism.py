"""Determinism tests for the high-level :class:`Engine` API."""

from engine import Engine


def _setup_engine() -> Engine:
    e = Engine()
    h = memoryview(b"\x00\x01\x02\x03")
    b = memoryview(b"\x04\x05")
    r = memoryview(b"\x06")
    e.enqueue_heightmap(h, b, r)
    e.enqueue_prop_descriptor([{ "type": "rock", "seed": 1 }])
    return e


def test_state_hashes_repeatable():
    frames = [0, 100, 500]
    a = _setup_engine()
    b = _setup_engine()
    assert a.run_and_snapshot(frames) == b.run_and_snapshot(frames)
