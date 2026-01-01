#include "seed_registry.h"

PCG64::PCG64(uint64_t seed, uint64_t seq) {
    state_ = 0;
    inc_ = ( (__uint128_t)seq << 1u) | 1u;
    (*this)();
    state_ += seed;
    (*this)();
}

uint64_t PCG64::operator()() {
    __uint128_t oldstate = state_;
    state_ = oldstate * (__uint128_t)6364136223846793005ULL + inc_;
    uint64_t xorshifted = (uint64_t)(((oldstate >> 64u) ^ oldstate) >> 5u);
    uint64_t rot = (uint64_t)(oldstate >> 122u);
    return (xorshifted >> rot) | (xorshifted << ((-rot) & 63u));
}

SeedRegistry::SeedRegistry(uint64_t root)
    : root_seed_(root), sm_state_(root), counter_(0), rng_(root) {}

uint64_t SeedRegistry::splitmix64(uint64_t &state) {
    uint64_t z = (state += 0x9E3779B97f4A7C15ULL);
    z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9ULL;
    z = (z ^ (z >> 27)) * 0x94D049BB133111EBULL;
    return z ^ (z >> 31);
}

uint64_t SeedRegistry::get_subseed(const std::string& name) {
    // Check if we already have a seed for this name
    auto it = named_seeds_.find(name);
    if (it != named_seeds_.end()) {
        return it->second;
    }

    // Generate a new deterministic seed for this name
    // Matches Python: seed_input = self.root_seed + self._counter
    counter_ += 1;
    uint64_t seed_input = root_seed_ + counter_;
    uint64_t subseed = splitmix64(seed_input);

    // Cache and return
    named_seeds_[name] = subseed;
    return subseed;
}

uint64_t SeedRegistry::get_subseed_sequential() {
    return splitmix64(sm_state_);
}

uint64_t SeedRegistry::next_u64() {
    return rng_();
}
