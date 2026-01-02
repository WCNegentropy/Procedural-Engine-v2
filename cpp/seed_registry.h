#pragma once
#include <cstdint>
#include <string>
#include <unordered_map>

// Portable 128-bit unsigned integer for PCG64
// Works on MSVC, GCC, and Clang
struct uint128_t {
    uint64_t lo;
    uint64_t hi;

    uint128_t() : lo(0), hi(0) {}
    uint128_t(uint64_t low) : lo(low), hi(0) {}
    uint128_t(uint64_t high, uint64_t low) : lo(low), hi(high) {}

    uint128_t operator+(const uint128_t& other) const {
        uint128_t result;
        result.lo = lo + other.lo;
        result.hi = hi + other.hi + (result.lo < lo ? 1 : 0);
        return result;
    }

    uint128_t operator*(const uint128_t& other) const {
        // 128-bit multiplication using 64-bit parts
        uint64_t a_lo = lo & 0xFFFFFFFF;
        uint64_t a_hi = lo >> 32;
        uint64_t b_lo = other.lo & 0xFFFFFFFF;
        uint64_t b_hi = other.lo >> 32;

        uint64_t p0 = a_lo * b_lo;
        uint64_t p1 = a_lo * b_hi;
        uint64_t p2 = a_hi * b_lo;
        uint64_t p3 = a_hi * b_hi;

        uint64_t carry = ((p0 >> 32) + (p1 & 0xFFFFFFFF) + (p2 & 0xFFFFFFFF)) >> 32;

        uint128_t result;
        result.lo = p0 + (p1 << 32) + (p2 << 32);
        result.hi = p3 + (p1 >> 32) + (p2 >> 32) + carry + hi * other.lo + lo * other.hi;
        return result;
    }

    uint128_t& operator+=(const uint128_t& other) {
        *this = *this + other;
        return *this;
    }

    uint64_t to_u64() const { return lo; }
    uint64_t high_bits() const { return hi; }
};

// SplitMix64 and PCG64-based SeedRegistry for deterministic RNG.
class PCG64 {
public:
    PCG64(uint64_t seed = 0, uint64_t seq = 1);
    uint64_t operator()();
private:
    uint128_t state_;
    uint128_t inc_;
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
