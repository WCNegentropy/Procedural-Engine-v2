#pragma once
#include <cstdint>
#include <string>
#include <unordered_map>

// SplitMix64 and PCG64-based SeedRegistry for deterministic RNG.
class PCG64 {
public:
    PCG64(uint64_t seed = 0, uint64_t seq = 1);
    uint64_t operator()();
private:
    __uint128_t state_;
    __uint128_t inc_;
};

class SeedRegistry {
public:
    explicit SeedRegistry(uint64_t root);

    /**
     * Get a deterministic sub-seed for a named subsystem.
     * Same name always returns the same sub-seed.
     * Matches Python's SeedRegistry.get_subseed(name: str) API.
     */
    uint64_t get_subseed(const std::string& name);

    /**
     * Get a sequential sub-seed (legacy API, for internal use).
     * Each call advances state and returns a new seed.
     */
    uint64_t get_subseed_sequential();

    uint64_t next_u64();

    /**
     * Get the root seed.
     */
    uint64_t root_seed() const { return root_seed_; }

private:
    uint64_t root_seed_;
    uint64_t sm_state_;
    uint64_t counter_;
    PCG64 rng_;
    std::unordered_map<std::string, uint64_t> named_seeds_;
    static uint64_t splitmix64(uint64_t &state);
};
