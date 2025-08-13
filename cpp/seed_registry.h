#pragma once
#include <cstdint>

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
    uint64_t get_subseed();
    uint64_t next_u64();
private:
    uint64_t sm_state_;
    PCG64 rng_;
    static uint64_t splitmix64(uint64_t &state);
};
