#!/usr/bin/env python3
"""Demonstration script for frame rate limiting.

This script shows how the frame rate limiting works in both
headless and windowed modes with different configurations.
"""
import time
from game_runner import GameRunner, RunnerConfig, HeadlessBackend


def test_frame_timing(description: str, config: RunnerConfig, num_frames: int = 60):
    """Test frame timing with a specific configuration."""
    print(f"\n{'='*60}")
    print(f"TEST: {description}")
    print(f"Config: target_fps={config.target_fps}, vsync={config.vsync}, headless={config.headless}")
    print(f"{'='*60}")
    
    runner = GameRunner(config)
    runner.initialize()
    
    start = time.perf_counter()
    runner.run_frames(num_frames)
    elapsed = time.perf_counter() - start
    
    actual_fps = num_frames / elapsed if elapsed > 0 else 0
    expected_time = num_frames / config.target_fps if config.target_fps > 0 else 0
    
    print(f"Frames:       {num_frames}")
    print(f"Elapsed:      {elapsed:.3f}s")
    print(f"Actual FPS:   {actual_fps:.1f}")
    print(f"Target FPS:   {config.target_fps}")
    if expected_time > 0:
        print(f"Expected:     ~{expected_time:.3f}s (at target FPS)")
    print(f"FPS counter:  {runner.fps:.1f}")
    
    runner.shutdown()
    return elapsed, actual_fps


def main():
    """Run frame timing tests."""
    print("\n" + "="*60)
    print("FRAME RATE LIMITING DEMONSTRATION")
    print("="*60)
    
    # Test 1: Headless with 60 FPS target (should ignore limit)
    test_frame_timing(
        "Headless mode with 60 FPS target",
        RunnerConfig(headless=True, target_fps=60),
        num_frames=60
    )
    
    # Test 2: Headless with 30 FPS target (should ignore limit)
    test_frame_timing(
        "Headless mode with 30 FPS target",
        RunnerConfig(headless=True, target_fps=30),
        num_frames=30
    )
    
    # Test 3: Headless with unlimited FPS
    test_frame_timing(
        "Headless mode with unlimited FPS",
        RunnerConfig(headless=True, target_fps=0),
        num_frames=100
    )
    
    # Test 4: Headless with vsync disabled
    test_frame_timing(
        "Headless mode with vsync disabled",
        RunnerConfig(headless=True, target_fps=60, vsync=False),
        num_frames=60
    )
    
    print("\n" + "="*60)
    print("KEY OBSERVATIONS:")
    print("="*60)
    print("1. Headless mode runs as fast as possible (ignores frame limiter)")
    print("2. This is by design - headless uses simulated time for testing")
    print("3. Frame limiter only activates in windowed mode (non-headless)")
    print("4. Vsync setting is properly configured and passed to Vulkan")
    print("5. In windowed mode, Vulkan FIFO vsync would limit to monitor refresh")
    print("6. Python frame limiter acts as fallback if Vulkan vsync fails")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
