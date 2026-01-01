#pragma once

#include <vulkan/vulkan.h>
#include <cstdint>
#include <vector>
#include <string>
#include <memory>
#include <unordered_map>
#include <array>
#include <optional>
#include "props.h"

/**
 * Graphics system with Vulkan backend.
 *
 * This module provides a complete Vulkan-based rendering pipeline including:
 * - Core Vulkan setup (instance, device, swapchain)
 * - GPU resource management (buffers, textures, memory)
 * - GLSL → SPIR-V shader compilation
 * - Render pipeline: Depth pre-pass → Clustered Forward+ → Post-processing
 * - Virtual texture system with 128 KB tiles and LRU paging
 * - Integration with terrain, props, and material systems
 */

namespace graphics {

// ============================================================================
// Forward Declarations
// ============================================================================

class GraphicsDevice;
class RenderContext;
class ShaderCompiler;
class VirtualTextureCache;

// ============================================================================
// GPU Buffer
// ============================================================================

/**
 * GPU buffer resource.
 */
struct GPUBuffer {
    VkBuffer buffer = VK_NULL_HANDLE;
    VkDeviceMemory memory = VK_NULL_HANDLE;
    VkDeviceSize size = 0;
    VkBufferUsageFlags usage = 0;
    void* mapped = nullptr;

    bool is_valid() const { return buffer != VK_NULL_HANDLE; }
};

/**
 * GPU image/texture resource.
 */
struct GPUImage {
    VkImage image = VK_NULL_HANDLE;
    VkDeviceMemory memory = VK_NULL_HANDLE;
    VkImageView view = VK_NULL_HANDLE;
    VkSampler sampler = VK_NULL_HANDLE;
    VkFormat format = VK_FORMAT_UNDEFINED;
    VkExtent2D extent = {0, 0};
    uint32_t mip_levels = 1;

    bool is_valid() const { return image != VK_NULL_HANDLE; }
};

/**
 * GPU mesh representation.
 */
struct GPUMesh {
    GPUBuffer vertex_buffer;
    GPUBuffer index_buffer;
    uint32_t vertex_count = 0;
    uint32_t index_count = 0;

    bool is_valid() const {
        return vertex_buffer.is_valid() && index_buffer.is_valid();
    }
};

// ============================================================================
// Shader & Pipeline
// ============================================================================

/**
 * Compiled SPIR-V shader module.
 */
struct ShaderModule {
    VkShaderModule module = VK_NULL_HANDLE;
    VkShaderStageFlagBits stage;
    std::vector<uint32_t> spirv_code;
    std::string entry_point = "main";

    bool is_valid() const { return module != VK_NULL_HANDLE; }
};

/**
 * Graphics pipeline configuration.
 */
struct PipelineConfig {
    std::string vertex_shader;
    std::string fragment_shader;
    VkPrimitiveTopology topology = VK_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST;
    VkCullModeFlags cull_mode = VK_CULL_MODE_BACK_BIT;
    bool depth_test = true;
    bool depth_write = true;
    VkCompareOp depth_compare = VK_COMPARE_OP_LESS;
};

/**
 * Graphics pipeline.
 */
struct Pipeline {
    VkPipeline pipeline = VK_NULL_HANDLE;
    VkPipelineLayout layout = VK_NULL_HANDLE;
    VkDescriptorSetLayout descriptor_layout = VK_NULL_HANDLE;
    uint64_t hash = 0;

    bool is_valid() const { return pipeline != VK_NULL_HANDLE; }
};

// ============================================================================
// Virtual Texture System
// ============================================================================

/**
 * Virtual texture tile (128 KB as per spec).
 */
struct VirtualTextureTile {
    uint32_t x = 0;
    uint32_t y = 0;
    uint32_t mip_level = 0;
    GPUImage gpu_image;
    uint64_t last_access_frame = 0;
    bool resident = false;
};

/**
 * Virtual texture page table entry.
 */
struct PageTableEntry {
    uint32_t physical_x = 0;
    uint32_t physical_y = 0;
    uint32_t mip_level = 0;
    bool resident = false;
};

/**
 * Virtual texture cache with LRU eviction.
 */
class VirtualTextureCache {
public:
    VirtualTextureCache(GraphicsDevice* device, uint32_t cache_size_mb = 256);
    ~VirtualTextureCache();

    /**
     * Request a tile (loads if not resident).
     */
    const VirtualTextureTile* request_tile(uint32_t x, uint32_t y, uint32_t mip);

    /**
     * Update frame counter for LRU tracking.
     */
    void advance_frame() { current_frame_++; }

    /**
     * Clear all cached tiles.
     */
    void clear();

private:
    GraphicsDevice* device_ = nullptr;
    uint64_t current_frame_ = 0;
    uint32_t max_tiles_ = 0;
    std::unordered_map<uint64_t, VirtualTextureTile> tiles_;

    uint64_t tile_key(uint32_t x, uint32_t y, uint32_t mip) const {
        return (uint64_t(mip) << 48) | (uint64_t(y) << 24) | uint64_t(x);
    }

    void evict_lru();
    void load_tile(VirtualTextureTile& tile);
};

// ============================================================================
// Shader Compiler (GLSL → SPIR-V)
// ============================================================================

/**
 * GLSL to SPIR-V shader compiler.
 */
class ShaderCompiler {
public:
    ShaderCompiler() = default;

    /**
     * Compile GLSL source to SPIR-V.
     *
     * @param source GLSL shader source code
     * @param stage Shader stage (vertex, fragment, etc.)
     * @param entry_point Entry point function name
     * @return SPIR-V bytecode, empty on failure
     */
    std::vector<uint32_t> compile_glsl(
        const std::string& source,
        VkShaderStageFlagBits stage,
        const std::string& entry_point = "main"
    );

    /**
     * Get last compilation error message.
     */
    const std::string& get_error() const { return last_error_; }

private:
    std::string last_error_;
};

// ============================================================================
// Graphics Device (Vulkan Core)
// ============================================================================

/**
 * Queue family indices.
 */
struct QueueFamilyIndices {
    std::optional<uint32_t> graphics_family;
    std::optional<uint32_t> present_family;
    std::optional<uint32_t> compute_family;

    bool is_complete() const {
        return graphics_family.has_value() && present_family.has_value();
    }
};

/**
 * Swapchain support details.
 */
struct SwapchainSupportDetails {
    VkSurfaceCapabilitiesKHR capabilities;
    std::vector<VkSurfaceFormatKHR> formats;
    std::vector<VkPresentModeKHR> present_modes;
};

/**
 * Core Vulkan graphics device.
 */
class GraphicsDevice {
public:
    GraphicsDevice();
    ~GraphicsDevice();

    /**
     * Initialize Vulkan with optional window surface.
     * For headless rendering, pass VK_NULL_HANDLE.
     */
    bool initialize(VkSurfaceKHR surface = VK_NULL_HANDLE, bool enable_validation = false);

    /**
     * Shutdown and cleanup all Vulkan resources.
     */
    void shutdown();

    // Resource creation
    GPUBuffer create_buffer(VkDeviceSize size, VkBufferUsageFlags usage,
                           VkMemoryPropertyFlags properties);
    void destroy_buffer(GPUBuffer& buffer);

    GPUImage create_image(uint32_t width, uint32_t height, VkFormat format,
                         VkImageUsageFlags usage, uint32_t mip_levels = 1);
    void destroy_image(GPUImage& image);

    GPUMesh upload_mesh(const props::Mesh& mesh);
    void destroy_mesh(GPUMesh& gpu_mesh);

    // Shader management
    ShaderModule create_shader_module(const std::vector<uint32_t>& spirv_code,
                                     VkShaderStageFlagBits stage);
    void destroy_shader_module(ShaderModule& shader);

    // Pipeline management
    Pipeline create_pipeline(const PipelineConfig& config, VkRenderPass render_pass);
    void destroy_pipeline(Pipeline& pipeline);

    // Memory mapping
    void* map_buffer(GPUBuffer& buffer);
    void unmap_buffer(GPUBuffer& buffer);
    void update_buffer(GPUBuffer& buffer, const void* data, VkDeviceSize size);

    // Command submission
    VkCommandBuffer begin_single_time_commands();
    void end_single_time_commands(VkCommandBuffer command_buffer);

    // Accessors
    VkDevice device() const { return device_; }
    VkPhysicalDevice physical_device() const { return physical_device_; }
    VkQueue graphics_queue() const { return graphics_queue_; }
    VkCommandPool command_pool() const { return command_pool_; }
    const QueueFamilyIndices& queue_families() const { return queue_families_; }

    bool is_initialized() const { return device_ != VK_NULL_HANDLE; }

private:
    // Vulkan core objects
    VkInstance instance_ = VK_NULL_HANDLE;
    VkDebugUtilsMessengerEXT debug_messenger_ = VK_NULL_HANDLE;
    VkPhysicalDevice physical_device_ = VK_NULL_HANDLE;
    VkDevice device_ = VK_NULL_HANDLE;
    VkSurfaceKHR surface_ = VK_NULL_HANDLE;

    // Queues
    VkQueue graphics_queue_ = VK_NULL_HANDLE;
    VkQueue present_queue_ = VK_NULL_HANDLE;
    VkQueue compute_queue_ = VK_NULL_HANDLE;
    QueueFamilyIndices queue_families_;

    // Command pools
    VkCommandPool command_pool_ = VK_NULL_HANDLE;

    // Swapchain (optional, for windowed rendering)
    VkSwapchainKHR swapchain_ = VK_NULL_HANDLE;
    std::vector<VkImage> swapchain_images_;
    std::vector<VkImageView> swapchain_image_views_;
    VkFormat swapchain_format_ = VK_FORMAT_UNDEFINED;
    VkExtent2D swapchain_extent_ = {0, 0};

    // Helper functions
    bool create_instance(bool enable_validation);
    bool setup_debug_messenger();
    bool pick_physical_device();
    bool create_logical_device();
    bool create_command_pool();

    QueueFamilyIndices find_queue_families(VkPhysicalDevice device);
    bool check_device_extension_support(VkPhysicalDevice device);
    SwapchainSupportDetails query_swapchain_support(VkPhysicalDevice device);
    uint32_t find_memory_type(uint32_t type_filter, VkMemoryPropertyFlags properties);

    std::vector<const char*> get_required_extensions(bool enable_validation);
    bool check_validation_layer_support();
};

// ============================================================================
// Render Context (High-Level Rendering)
// ============================================================================

/**
 * Render statistics.
 */
struct RenderStats {
    uint32_t draw_calls = 0;
    uint32_t triangles = 0;
    uint32_t vertices = 0;
    float frame_time_ms = 0.0f;
};

/**
 * Camera parameters.
 */
struct Camera {
    std::array<float, 3> position = {0.0f, 10.0f, 10.0f};
    std::array<float, 3> target = {0.0f, 0.0f, 0.0f};
    std::array<float, 3> up = {0.0f, 1.0f, 0.0f};
    float fov = 60.0f;
    float near_plane = 0.1f;
    float far_plane = 1000.0f;
};

/**
 * Light data for clustered forward+.
 */
struct Light {
    std::array<float, 3> position;
    float radius;
    std::array<float, 3> color;
    float intensity;
};

/**
 * High-level render context managing the full render pipeline.
 */
class RenderContext {
public:
    explicit RenderContext(GraphicsDevice* device);
    ~RenderContext();

    /**
     * Initialize render passes and framebuffers.
     */
    bool initialize(uint32_t width, uint32_t height);

    /**
     * Begin a new frame.
     */
    void begin_frame();

    /**
     * Render a mesh with a material.
     */
    void draw_mesh(const GPUMesh& mesh, const Pipeline& material_pipeline,
                   const std::array<float, 16>& transform);

    /**
     * Render terrain heightfield.
     */
    void draw_terrain(const GPUMesh& terrain_mesh, const Pipeline& pipeline);

    /**
     * End frame and present.
     */
    void end_frame();

    /**
     * Set camera parameters.
     */
    void set_camera(const Camera& camera) { camera_ = camera; }

    /**
     * Add a light to the scene.
     */
    void add_light(const Light& light) { lights_.push_back(light); }

    /**
     * Clear all lights.
     */
    void clear_lights() { lights_.clear(); }

    /**
     * Get render statistics.
     */
    const RenderStats& stats() const { return stats_; }

    /**
     * Resize framebuffers.
     */
    void resize(uint32_t width, uint32_t height);

private:
    GraphicsDevice* device_ = nullptr;

    // Render passes
    VkRenderPass depth_prepass_ = VK_NULL_HANDLE;
    VkRenderPass forward_pass_ = VK_NULL_HANDLE;
    VkRenderPass post_pass_ = VK_NULL_HANDLE;

    // Framebuffers
    VkFramebuffer depth_framebuffer_ = VK_NULL_HANDLE;
    VkFramebuffer forward_framebuffer_ = VK_NULL_HANDLE;
    VkFramebuffer post_framebuffer_ = VK_NULL_HANDLE;

    // Render targets
    GPUImage depth_image_;
    GPUImage color_image_;
    GPUImage post_image_;

    // Command buffers
    VkCommandBuffer command_buffer_ = VK_NULL_HANDLE;

    // Synchronization
    VkSemaphore image_available_semaphore_ = VK_NULL_HANDLE;
    VkSemaphore render_finished_semaphore_ = VK_NULL_HANDLE;
    VkFence in_flight_fence_ = VK_NULL_HANDLE;

    // Scene data
    Camera camera_;
    std::vector<Light> lights_;
    RenderStats stats_;

    // Frame state
    uint32_t width_ = 0;
    uint32_t height_ = 0;
    uint64_t frame_number_ = 0;

    // Helper functions
    bool create_render_passes();
    bool create_framebuffers();
    bool create_sync_objects();
    void cleanup_framebuffers();
};

// ============================================================================
// Graphics System (Main Interface)
// ============================================================================

/**
 * Main graphics system interface.
 */
class GraphicsSystem {
public:
    GraphicsSystem();
    ~GraphicsSystem();

    /**
     * Initialize the graphics system.
     *
     * @param width Render target width
     * @param height Render target height
     * @param enable_validation Enable Vulkan validation layers
     * @return true on success
     */
    bool initialize(uint32_t width = 1920, uint32_t height = 1080,
                   bool enable_validation = false);

    /**
     * Shutdown the graphics system.
     */
    void shutdown();

    /**
     * Upload a mesh to GPU.
     */
    GPUMesh upload_mesh(const props::Mesh& mesh);

    /**
     * Create a material pipeline from GLSL shaders.
     */
    Pipeline create_material_pipeline(const std::string& vertex_glsl,
                                     const std::string& fragment_glsl);

    /**
     * Begin rendering a frame.
     */
    void begin_frame();

    /**
     * Draw a mesh with transform.
     */
    void draw_mesh(const GPUMesh& mesh, const Pipeline& pipeline,
                   const std::array<float, 16>& transform);

    /**
     * End frame and present.
     */
    void end_frame();

    /**
     * Set camera.
     */
    void set_camera(const Camera& camera);

    /**
     * Add light to scene.
     */
    void add_light(const Light& light);

    /**
     * Get render statistics.
     */
    const RenderStats& get_stats() const;

    /**
     * Check if initialized.
     */
    bool is_initialized() const { return device_ && device_->is_initialized(); }

private:
    std::unique_ptr<GraphicsDevice> device_;
    std::unique_ptr<RenderContext> render_context_;
    std::unique_ptr<ShaderCompiler> shader_compiler_;
    std::unique_ptr<VirtualTextureCache> texture_cache_;
};

} // namespace graphics
