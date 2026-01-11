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
 * Vertex format for mesh rendering.
 */
struct Vertex {
    float position[3];
    float normal[3];
    float uv[2];
    
    static VkVertexInputBindingDescription get_binding_description() {
        VkVertexInputBindingDescription binding{};
        binding.binding = 0;
        binding.stride = sizeof(Vertex);
        binding.inputRate = VK_VERTEX_INPUT_RATE_VERTEX;
        return binding;
    }
    
    static std::array<VkVertexInputAttributeDescription, 3> get_attribute_descriptions() {
        std::array<VkVertexInputAttributeDescription, 3> attrs{};
        // Position
        attrs[0].binding = 0;
        attrs[0].location = 0;
        attrs[0].format = VK_FORMAT_R32G32B32_SFLOAT;
        attrs[0].offset = offsetof(Vertex, position);
        // Normal
        attrs[1].binding = 0;
        attrs[1].location = 1;
        attrs[1].format = VK_FORMAT_R32G32B32_SFLOAT;
        attrs[1].offset = offsetof(Vertex, normal);
        // UV
        attrs[2].binding = 0;
        attrs[2].location = 2;
        attrs[2].format = VK_FORMAT_R32G32_SFLOAT;
        attrs[2].offset = offsetof(Vertex, uv);
        return attrs;
    }
};

/**
 * Uniform buffer for per-frame data (camera, lighting).
 */
struct FrameUniforms {
    float view[16];           // View matrix
    float projection[16];      // Projection matrix
    float view_projection[16]; // Combined VP matrix
    float camera_pos[4];       // Camera position (w unused)
    float time[4];             // Time data: x=total, y=delta, z=frame, w=unused
};

/**
 * Uniform buffer for per-object data (transforms).
 */
struct ObjectUniforms {
    float model[16];          // Model matrix
    float normal_matrix[16];  // Normal matrix (inverse transpose of model)
};

/**
 * Push constants for quick per-draw updates.
 */
struct PushConstants {
    float model[16];          // Model transform
    float color[4];           // Base color / tint
};

/**
 * Graphics pipeline configuration.
 */
struct PipelineConfig {
    std::string vertex_shader;
    std::string fragment_shader;
    VkPrimitiveTopology topology = VK_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST;
    VkCullModeFlags cull_mode = VK_CULL_MODE_BACK_BIT;
    VkPolygonMode polygon_mode = VK_POLYGON_MODE_FILL;
    bool depth_test = true;
    bool depth_write = true;
    VkCompareOp depth_compare = VK_COMPARE_OP_LESS;
    bool blend_enable = false;
    VkBlendFactor src_blend = VK_BLEND_FACTOR_SRC_ALPHA;
    VkBlendFactor dst_blend = VK_BLEND_FACTOR_ONE_MINUS_SRC_ALPHA;
};

/**
 * Graphics pipeline.
 */
struct Pipeline {
    VkPipeline pipeline = VK_NULL_HANDLE;
    VkPipelineLayout layout = VK_NULL_HANDLE;
    VkDescriptorSetLayout descriptor_layout = VK_NULL_HANDLE;
    ShaderModule vertex_shader;
    ShaderModule fragment_shader;
    uint64_t hash = 0;

    bool is_valid() const { return pipeline != VK_NULL_HANDLE && layout != VK_NULL_HANDLE; }
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
     * @param surface Vulkan surface for windowed rendering (VK_NULL_HANDLE for headless)
     * @param enable_validation Enable Vulkan validation layers
     * @param enable_vsync Enable vsync (FIFO present mode), otherwise prefer MAILBOX
     */
    bool initialize(VkSurfaceKHR surface = VK_NULL_HANDLE, bool enable_validation = false, bool enable_vsync = true);

    /**
     * Create only the Vulkan instance with specified extensions.
     * Use this for two-phase initialization where a surface needs to be created
     * from the instance before completing initialization.
     * @param extensions List of required instance extensions
     * @param enable_validation Enable Vulkan validation layers
     * @return true on success
     */
    bool create_instance_with_extensions(const std::vector<std::string>& extensions, bool enable_validation = false);

    /**
     * Complete initialization after instance and surface creation.
     * Call this after create_instance_with_extensions and creating a surface.
     * @param surface The Vulkan surface created from the instance
     * @param enable_vsync Enable vsync (FIFO present mode)
     * @return true on success
     */
    bool complete_initialization(VkSurfaceKHR surface, bool enable_vsync = true);

    /**
     * Get the instance handle as a 64-bit integer for FFI.
     * @return VkInstance cast to uint64_t, or 0 if not initialized
     */
    uint64_t get_instance_handle() const { return reinterpret_cast<uint64_t>(instance_); }

    /**
     * Shutdown and cleanup all Vulkan resources.
     */
    void shutdown();

    /**
     * Create a swapchain for windowed rendering.
     */
    bool create_swapchain(uint32_t width, uint32_t height);
    
    /**
     * Recreate swapchain after window resize.
     */
    bool recreate_swapchain(uint32_t width, uint32_t height);

    // Resource creation
    GPUBuffer create_buffer(VkDeviceSize size, VkBufferUsageFlags usage,
                           VkMemoryPropertyFlags properties);
    void destroy_buffer(GPUBuffer& buffer);

    GPUImage create_image(uint32_t width, uint32_t height, VkFormat format,
                         VkImageUsageFlags usage, uint32_t mip_levels = 1);
    void destroy_image(GPUImage& image);
    
    /**
     * Create a sampler for texture sampling.
     */
    VkSampler create_sampler(VkFilter filter = VK_FILTER_LINEAR, 
                            VkSamplerAddressMode address_mode = VK_SAMPLER_ADDRESS_MODE_REPEAT,
                            float max_anisotropy = 16.0f);

    GPUMesh upload_mesh(const props::Mesh& mesh);
    void destroy_mesh(GPUMesh& gpu_mesh);

    // Shader management
    ShaderModule create_shader_module(const std::vector<uint32_t>& spirv_code,
                                     VkShaderStageFlagBits stage);
    void destroy_shader_module(ShaderModule& shader);

    // Pipeline management
    Pipeline create_pipeline(const PipelineConfig& config, VkRenderPass render_pass,
                            const std::vector<uint32_t>& vertex_spirv,
                            const std::vector<uint32_t>& fragment_spirv);
    void destroy_pipeline(Pipeline& pipeline);
    
    // Descriptor management
    VkDescriptorPool create_descriptor_pool(uint32_t max_sets, 
                                           const std::vector<VkDescriptorPoolSize>& pool_sizes);
    VkDescriptorSet allocate_descriptor_set(VkDescriptorPool pool, 
                                           VkDescriptorSetLayout layout);
    void update_descriptor_set(VkDescriptorSet set, uint32_t binding,
                              VkDescriptorType type, const GPUBuffer& buffer);
    void update_descriptor_set(VkDescriptorSet set, uint32_t binding,
                              const GPUImage& image, VkSampler sampler);

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
    VkQueue present_queue() const { return present_queue_; }
    VkCommandPool command_pool() const { return command_pool_; }
    VkInstance instance() const { return instance_; }
    VkSurfaceKHR surface() const { return surface_; }
    VkSwapchainKHR swapchain() const { return swapchain_; }
    VkFormat swapchain_format() const { return swapchain_format_; }
    VkExtent2D swapchain_extent() const { return swapchain_extent_; }
    const std::vector<VkImageView>& swapchain_image_views() const { return swapchain_image_views_; }
    const QueueFamilyIndices& queue_families() const { return queue_families_; }

    bool is_initialized() const { return device_ != VK_NULL_HANDLE; }
    bool has_swapchain() const { return swapchain_ != VK_NULL_HANDLE; }

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
    bool enable_vsync_ = true;  // Prefer FIFO (vsync) over MAILBOX

    // Helper functions
    bool create_instance(bool enable_validation);
    bool create_instance_impl(const std::vector<const char*>& extensions, bool enable_validation);
    bool setup_debug_messenger();
    bool pick_physical_device();
    bool create_logical_device();
    bool create_command_pool();
    void cleanup_swapchain();

    QueueFamilyIndices find_queue_families(VkPhysicalDevice device);
    bool check_device_extension_support(VkPhysicalDevice device);
    SwapchainSupportDetails query_swapchain_support(VkPhysicalDevice device);
    uint32_t find_memory_type(uint32_t type_filter, VkMemoryPropertyFlags properties);
    VkSurfaceFormatKHR choose_swap_surface_format(const std::vector<VkSurfaceFormatKHR>& formats);
    VkPresentModeKHR choose_swap_present_mode(const std::vector<VkPresentModeKHR>& modes);
    VkExtent2D choose_swap_extent(const VkSurfaceCapabilitiesKHR& capabilities, 
                                  uint32_t width, uint32_t height);
    
    // Store validation flag for two-phase init
    bool enable_validation_ = false;

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
 * Queued draw command for deferred rendering.
 */
struct DrawCommand {
    const GPUMesh* mesh;
    const Pipeline* pipeline;
    std::array<float, 16> transform;
    std::array<float, 4> color;
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
     * @return Image index acquired from swapchain (or 0 for headless)
     */
    uint32_t begin_frame();

    /**
     * Queue a mesh for rendering.
     */
    void draw_mesh(const GPUMesh& mesh, const Pipeline& material_pipeline,
                   const std::array<float, 16>& transform);

    /**
     * Render terrain heightfield.
     */
    void draw_terrain(const GPUMesh& terrain_mesh, const Pipeline& pipeline);

    /**
     * Execute all queued draw commands.
     */
    void flush_draws();

    /**
     * End frame and present.
     */
    void end_frame();

    /**
     * Set camera parameters.
     */
    void set_camera(const Camera& camera) { camera_ = camera; update_camera_uniforms(); }

    /**
     * Add a light to the scene.
     */
    void add_light(const Light& light) { if (lights_.size() < MAX_LIGHTS) lights_.push_back(light); }

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
    
    /**
     * Get the main render pass (for pipeline creation).
     */
    VkRenderPass render_pass() const { return forward_pass_; }
    
    /**
     * Get current frame's command buffer (for external command recording).
     */
    VkCommandBuffer command_buffer() const { return command_buffers_[current_frame_]; }

    static constexpr uint32_t MAX_FRAMES_IN_FLIGHT = 2;
    static constexpr uint32_t MAX_LIGHTS = 128;

private:
    GraphicsDevice* device_ = nullptr;

    // Render passes
    VkRenderPass depth_prepass_ = VK_NULL_HANDLE;
    VkRenderPass forward_pass_ = VK_NULL_HANDLE;
    VkRenderPass post_pass_ = VK_NULL_HANDLE;

    // Framebuffers (one per swapchain image or single for headless)
    std::vector<VkFramebuffer> swapchain_framebuffers_;
    VkFramebuffer depth_framebuffer_ = VK_NULL_HANDLE;
    VkFramebuffer post_framebuffer_ = VK_NULL_HANDLE;

    // Render targets
    GPUImage depth_image_;
    GPUImage color_image_;
    GPUImage post_image_;
    GPUImage resolve_image_;  // For MSAA resolve

    // Per-frame resources
    std::vector<VkCommandBuffer> command_buffers_;
    std::vector<VkSemaphore> image_available_semaphores_;
    std::vector<VkSemaphore> render_finished_semaphores_;
    std::vector<VkFence> in_flight_fences_;
    
    // Uniform buffers (per frame)
    std::vector<GPUBuffer> frame_uniform_buffers_;
    
    // Descriptor pool and sets
    VkDescriptorPool descriptor_pool_ = VK_NULL_HANDLE;
    VkDescriptorSetLayout frame_descriptor_layout_ = VK_NULL_HANDLE;
    std::vector<VkDescriptorSet> frame_descriptor_sets_;

    // Scene data
    Camera camera_;
    std::vector<Light> lights_;
    std::vector<DrawCommand> draw_queue_;
    RenderStats stats_;

    // Frame state
    uint32_t width_ = 0;
    uint32_t height_ = 0;
    uint64_t frame_number_ = 0;
    uint32_t current_frame_ = 0;  // Index for frames in flight
    uint32_t current_image_index_ = 0;  // Swapchain image index
    bool frame_started_ = false;

    // Helper functions
    bool create_render_passes();
    bool create_framebuffers();
    bool create_sync_objects();
    bool create_command_buffers();
    bool create_uniform_buffers();
    bool create_descriptor_resources();
    void cleanup_framebuffers();
    void update_camera_uniforms();
    void record_draw_commands();
    
    // Matrix utilities
    void compute_view_matrix(float* out, const Camera& cam);
    void compute_projection_matrix(float* out, float fov, float aspect, float near, float far);
    void multiply_matrices(float* out, const float* a, const float* b);
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
     * @param enable_vsync Enable vsync (FIFO present mode)
     * @return true on success
     */
    bool initialize(uint32_t width = 1920, uint32_t height = 1080,
                   bool enable_validation = false, bool enable_vsync = true);
    
    /**
     * Initialize with window surface for windowed rendering.
     * @param enable_vsync Enable vsync (FIFO present mode)
     */
    bool initialize_with_surface(VkSurfaceKHR surface, uint32_t width, uint32_t height,
                                bool enable_validation = false, bool enable_vsync = true);

    /**
     * Create Vulkan instance with specified extensions (phase 1 of two-phase init).
     * Use this when you need to create a surface from the instance before completing init.
     * @param extensions List of required instance extension names
     * @param enable_validation Enable Vulkan validation layers
     * @return true on success
     */
    bool create_instance_with_extensions(const std::vector<std::string>& extensions,
                                         bool enable_validation = false);

    /**
     * Complete initialization with a surface (phase 2 of two-phase init).
     * Call this after create_instance_with_extensions and creating a surface.
     * @param surface The VkSurfaceKHR handle (as uint64_t for FFI)
     * @param width Render target width
     * @param height Render target height
     * @param enable_vsync Enable vsync
     * @return true on success
     */
    bool complete_initialization_with_surface(uint64_t surface, uint32_t width,
                                              uint32_t height, bool enable_vsync = true);

    /**
     * Get the Vulkan instance handle (as uint64_t for FFI).
     * @return Instance handle, or 0 if not initialized
     */
    uint64_t get_instance_handle() const;

    /**
     * Shutdown the graphics system.
     */
    void shutdown();
    
    /**
     * Resize the render targets.
     */
    void resize(uint32_t width, uint32_t height);

    /**
     * Upload a mesh to GPU.
     */
    GPUMesh upload_mesh(const props::Mesh& mesh);
    
    /**
     * Destroy a mesh and free GPU resources.
     */
    void destroy_mesh(GPUMesh& mesh);

    /**
     * Create a material pipeline from GLSL shaders.
     */
    Pipeline create_material_pipeline(const std::string& vertex_glsl,
                                     const std::string& fragment_glsl);
    
    /**
     * Destroy a pipeline.
     */
    void destroy_pipeline(Pipeline& pipeline);
    
    /**
     * Create default shaders for basic rendering.
     */
    Pipeline create_default_pipeline();

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
     * Draw a mesh with transform and color.
     */
    void draw_mesh(const GPUMesh& mesh, const Pipeline& pipeline,
                   const std::array<float, 16>& transform,
                   const std::array<float, 4>& color);

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
     * Clear all lights from the scene.
     */
    void clear_lights();

    /**
     * Get render statistics.
     */
    const RenderStats& get_stats() const;

    /**
     * Check if initialized.
     */
    bool is_initialized() const { return device_ && device_->is_initialized(); }
    
    /**
     * Get underlying device (for advanced usage).
     */
    GraphicsDevice* device() { return device_.get(); }
    
    /**
     * Get render context (for advanced usage).
     */
    RenderContext* render_context() { return render_context_.get(); }

private:
    std::unique_ptr<GraphicsDevice> device_;
    std::unique_ptr<RenderContext> render_context_;
    std::unique_ptr<ShaderCompiler> shader_compiler_;
    std::unique_ptr<VirtualTextureCache> texture_cache_;
    
    // Default resources
    Pipeline default_pipeline_;
    bool default_pipeline_created_ = false;
    
    // Create default shaders source
    std::string get_default_vertex_shader() const;
    std::string get_default_fragment_shader() const;
};

} // namespace graphics
