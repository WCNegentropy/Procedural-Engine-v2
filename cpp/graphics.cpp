#include "graphics.h"
#include <shaderc/shaderc.hpp>
#include <cstring>
#include <cmath>
#include <algorithm>
#include <stdexcept>
#include <set>
#include <iostream>

// Dear ImGui integration
#include "imgui.h"
#include "imgui_impl_vulkan.h"
#if HAS_SDL2
#include "imgui_impl_sdl2.h"
#include <SDL.h>
#endif

namespace graphics {

// Debug logging control - set to false for production builds
static constexpr bool ENABLE_DEBUG_LOGGING = true;

// Helper macro for conditional debug output
#define DEBUG_LOG(msg) do { if (ENABLE_DEBUG_LOGGING) { std::cout << msg << std::endl; } } while(0)

// ============================================================================
// Validation Layer Helpers
// ============================================================================

static const std::vector<const char*> VALIDATION_LAYERS = {
    "VK_LAYER_KHRONOS_validation"
};

static const std::vector<const char*> DEVICE_EXTENSIONS = {
    VK_KHR_SWAPCHAIN_EXTENSION_NAME
};

static VKAPI_ATTR VkBool32 VKAPI_CALL debug_callback(
    VkDebugUtilsMessageSeverityFlagBitsEXT severity,
    VkDebugUtilsMessageTypeFlagsEXT type,
    const VkDebugUtilsMessengerCallbackDataEXT* callback_data,
    void* user_data)
{
    if (severity >= VK_DEBUG_UTILS_MESSAGE_SEVERITY_WARNING_BIT_EXT) {
        std::cerr << "[Vulkan] " << callback_data->pMessage << std::endl;
    }
    return VK_FALSE;
}

// ============================================================================
// GraphicsDevice Implementation
// ============================================================================

GraphicsDevice::GraphicsDevice() = default;

GraphicsDevice::~GraphicsDevice() {
    shutdown();
}

bool GraphicsDevice::initialize(VkSurfaceKHR surface, bool enable_validation, bool enable_vsync) {
    surface_ = surface;
    enable_vsync_ = enable_vsync;
    enable_validation_ = enable_validation;

    if (!create_instance(enable_validation)) return false;
    if (enable_validation && !setup_debug_messenger()) return false;
    if (!pick_physical_device()) return false;
    if (!create_logical_device()) return false;
    if (!create_command_pool()) return false;

    return true;
}

bool GraphicsDevice::create_instance_with_extensions(const std::vector<std::string>& extensions,
                                                     bool enable_validation) {
    enable_validation_ = enable_validation;
    
    // Convert string extensions to const char* for Vulkan API
    // Note: The ext_ptrs vector's c_str() pointers remain valid because
    // the extensions vector is passed by const reference and stays alive
    // until create_instance_impl() completes
    std::vector<const char*> ext_ptrs;
    ext_ptrs.reserve(extensions.size() + 1);  // +1 for potential debug extension
    for (const auto& ext : extensions) {
        ext_ptrs.push_back(ext.c_str());
    }
    
    // Add debug extension if validation is enabled
    if (enable_validation) {
        ext_ptrs.push_back(VK_EXT_DEBUG_UTILS_EXTENSION_NAME);
    }
    
    return create_instance_impl(ext_ptrs, enable_validation);
}

bool GraphicsDevice::complete_initialization(VkSurfaceKHR surface, bool enable_vsync) {
    if (instance_ == VK_NULL_HANDLE) {
        std::cerr << "Cannot complete initialization: instance not created" << std::endl;
        return false;
    }
    
    surface_ = surface;
    enable_vsync_ = enable_vsync;
    
    if (enable_validation_ && debug_messenger_ == VK_NULL_HANDLE) {
        if (!setup_debug_messenger()) return false;
    }
    if (!pick_physical_device()) return false;
    if (!create_logical_device()) return false;
    if (!create_command_pool()) return false;

    return true;
}

void GraphicsDevice::shutdown() {
    if (device_ == VK_NULL_HANDLE) return;

    vkDeviceWaitIdle(device_);

    // Cleanup swapchain
    for (auto view : swapchain_image_views_) {
        vkDestroyImageView(device_, view, nullptr);
    }
    swapchain_image_views_.clear();

    if (swapchain_ != VK_NULL_HANDLE) {
        vkDestroySwapchainKHR(device_, swapchain_, nullptr);
        swapchain_ = VK_NULL_HANDLE;
    }

    // Cleanup command pool
    if (command_pool_ != VK_NULL_HANDLE) {
        vkDestroyCommandPool(device_, command_pool_, nullptr);
        command_pool_ = VK_NULL_HANDLE;
    }

    // Cleanup device
    if (device_ != VK_NULL_HANDLE) {
        vkDestroyDevice(device_, nullptr);
        device_ = VK_NULL_HANDLE;
    }

    // Cleanup debug messenger
    if (debug_messenger_ != VK_NULL_HANDLE) {
        auto func = (PFN_vkDestroyDebugUtilsMessengerEXT)vkGetInstanceProcAddr(
            instance_, "vkDestroyDebugUtilsMessengerEXT");
        if (func != nullptr) {
            func(instance_, debug_messenger_, nullptr);
        }
        debug_messenger_ = VK_NULL_HANDLE;
    }

    // Cleanup instance
    if (instance_ != VK_NULL_HANDLE) {
        vkDestroyInstance(instance_, nullptr);
        instance_ = VK_NULL_HANDLE;
    }
}

bool GraphicsDevice::create_instance(bool enable_validation) {
    auto extensions = get_required_extensions(enable_validation);
    return create_instance_impl(extensions, enable_validation);
}

bool GraphicsDevice::create_instance_impl(const std::vector<const char*>& extensions,
                                          bool enable_validation) {
    if (enable_validation && !check_validation_layer_support()) {
        std::cerr << "Validation layers requested but not available" << std::endl;
        return false;
    }

    VkApplicationInfo app_info{};
    app_info.sType = VK_STRUCTURE_TYPE_APPLICATION_INFO;
    app_info.pApplicationName = "Procedural Engine";
    app_info.applicationVersion = VK_MAKE_VERSION(1, 0, 0);
    app_info.pEngineName = "Procedural Engine";
    app_info.engineVersion = VK_MAKE_VERSION(1, 0, 0);
    app_info.apiVersion = VK_API_VERSION_1_2;

    VkInstanceCreateInfo create_info{};
    create_info.sType = VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO;
    create_info.pApplicationInfo = &app_info;

    create_info.enabledExtensionCount = static_cast<uint32_t>(extensions.size());
    create_info.ppEnabledExtensionNames = extensions.data();

    VkDebugUtilsMessengerCreateInfoEXT debug_create_info{};
    if (enable_validation) {
        create_info.enabledLayerCount = static_cast<uint32_t>(VALIDATION_LAYERS.size());
        create_info.ppEnabledLayerNames = VALIDATION_LAYERS.data();

        debug_create_info.sType = VK_STRUCTURE_TYPE_DEBUG_UTILS_MESSENGER_CREATE_INFO_EXT;
        debug_create_info.messageSeverity =
            VK_DEBUG_UTILS_MESSAGE_SEVERITY_VERBOSE_BIT_EXT |
            VK_DEBUG_UTILS_MESSAGE_SEVERITY_WARNING_BIT_EXT |
            VK_DEBUG_UTILS_MESSAGE_SEVERITY_ERROR_BIT_EXT;
        debug_create_info.messageType =
            VK_DEBUG_UTILS_MESSAGE_TYPE_GENERAL_BIT_EXT |
            VK_DEBUG_UTILS_MESSAGE_TYPE_VALIDATION_BIT_EXT |
            VK_DEBUG_UTILS_MESSAGE_TYPE_PERFORMANCE_BIT_EXT;
        debug_create_info.pfnUserCallback = debug_callback;
        create_info.pNext = &debug_create_info;
    } else {
        create_info.enabledLayerCount = 0;
        create_info.pNext = nullptr;
    }

    VkResult result = vkCreateInstance(&create_info, nullptr, &instance_);
    if (result != VK_SUCCESS) {
        std::cerr << "Failed to create Vulkan instance: " << result << std::endl;
        return false;
    }

    std::cout << "Vulkan instance created with " << extensions.size() << " extensions" << std::endl;
    return true;
}

bool GraphicsDevice::setup_debug_messenger() {
    VkDebugUtilsMessengerCreateInfoEXT create_info{};
    create_info.sType = VK_STRUCTURE_TYPE_DEBUG_UTILS_MESSENGER_CREATE_INFO_EXT;
    create_info.messageSeverity =
        VK_DEBUG_UTILS_MESSAGE_SEVERITY_VERBOSE_BIT_EXT |
        VK_DEBUG_UTILS_MESSAGE_SEVERITY_WARNING_BIT_EXT |
        VK_DEBUG_UTILS_MESSAGE_SEVERITY_ERROR_BIT_EXT;
    create_info.messageType =
        VK_DEBUG_UTILS_MESSAGE_TYPE_GENERAL_BIT_EXT |
        VK_DEBUG_UTILS_MESSAGE_TYPE_VALIDATION_BIT_EXT |
        VK_DEBUG_UTILS_MESSAGE_TYPE_PERFORMANCE_BIT_EXT;
    create_info.pfnUserCallback = debug_callback;

    auto func = (PFN_vkCreateDebugUtilsMessengerEXT)vkGetInstanceProcAddr(
        instance_, "vkCreateDebugUtilsMessengerEXT");
    if (func == nullptr) {
        std::cerr << "Failed to load vkCreateDebugUtilsMessengerEXT" << std::endl;
        return false;
    }

    VkResult result = func(instance_, &create_info, nullptr, &debug_messenger_);
    if (result != VK_SUCCESS) {
        std::cerr << "Failed to set up debug messenger: " << result << std::endl;
        return false;
    }

    return true;
}

bool GraphicsDevice::pick_physical_device() {
    uint32_t device_count = 0;
    vkEnumeratePhysicalDevices(instance_, &device_count, nullptr);

    if (device_count == 0) {
        std::cerr << "Failed to find GPUs with Vulkan support" << std::endl;
        return false;
    }

    std::vector<VkPhysicalDevice> devices(device_count);
    vkEnumeratePhysicalDevices(instance_, &device_count, devices.data());

    // Pick the first suitable device (discrete GPU preferred)
    for (const auto& device : devices) {
        VkPhysicalDeviceProperties props;
        vkGetPhysicalDeviceProperties(device, &props);

        VkPhysicalDeviceFeatures features;
        vkGetPhysicalDeviceFeatures(device, &features);

        QueueFamilyIndices indices = find_queue_families(device);
        bool extensions_supported = check_device_extension_support(device);

        if (indices.is_complete() && extensions_supported) {
            physical_device_ = device;
            queue_families_ = indices;
            std::cout << "Selected GPU: " << props.deviceName << std::endl;
            return true;
        }
    }

    std::cerr << "Failed to find a suitable GPU" << std::endl;
    return false;
}

bool GraphicsDevice::create_logical_device() {
    std::vector<VkDeviceQueueCreateInfo> queue_create_infos;
    std::set<uint32_t> unique_queue_families = {
        queue_families_.graphics_family.value()
    };

    if (queue_families_.present_family.has_value()) {
        unique_queue_families.insert(queue_families_.present_family.value());
    }
    if (queue_families_.compute_family.has_value()) {
        unique_queue_families.insert(queue_families_.compute_family.value());
    }

    float queue_priority = 1.0f;
    for (uint32_t queue_family : unique_queue_families) {
        VkDeviceQueueCreateInfo queue_create_info{};
        queue_create_info.sType = VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO;
        queue_create_info.queueFamilyIndex = queue_family;
        queue_create_info.queueCount = 1;
        queue_create_info.pQueuePriorities = &queue_priority;
        queue_create_infos.push_back(queue_create_info);
    }

    VkPhysicalDeviceFeatures device_features{};
    device_features.samplerAnisotropy = VK_TRUE;
    device_features.fillModeNonSolid = VK_TRUE;

    VkDeviceCreateInfo create_info{};
    create_info.sType = VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO;
    create_info.queueCreateInfoCount = static_cast<uint32_t>(queue_create_infos.size());
    create_info.pQueueCreateInfos = queue_create_infos.data();
    create_info.pEnabledFeatures = &device_features;
    create_info.enabledExtensionCount = static_cast<uint32_t>(DEVICE_EXTENSIONS.size());
    create_info.ppEnabledExtensionNames = DEVICE_EXTENSIONS.data();
    create_info.enabledLayerCount = 0;

    VkResult result = vkCreateDevice(physical_device_, &create_info, nullptr, &device_);
    if (result != VK_SUCCESS) {
        std::cerr << "Failed to create logical device: " << result << std::endl;
        return false;
    }

    // Get queue handles
    vkGetDeviceQueue(device_, queue_families_.graphics_family.value(), 0, &graphics_queue_);
    if (queue_families_.present_family.has_value()) {
        vkGetDeviceQueue(device_, queue_families_.present_family.value(), 0, &present_queue_);
    }
    if (queue_families_.compute_family.has_value()) {
        vkGetDeviceQueue(device_, queue_families_.compute_family.value(), 0, &compute_queue_);
    }

    return true;
}

bool GraphicsDevice::create_command_pool() {
    VkCommandPoolCreateInfo pool_info{};
    pool_info.sType = VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO;
    pool_info.queueFamilyIndex = queue_families_.graphics_family.value();
    pool_info.flags = VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT;

    VkResult result = vkCreateCommandPool(device_, &pool_info, nullptr, &command_pool_);
    if (result != VK_SUCCESS) {
        std::cerr << "Failed to create command pool: " << result << std::endl;
        return false;
    }

    return true;
}

QueueFamilyIndices GraphicsDevice::find_queue_families(VkPhysicalDevice device) {
    QueueFamilyIndices indices;

    uint32_t queue_family_count = 0;
    vkGetPhysicalDeviceQueueFamilyProperties(device, &queue_family_count, nullptr);

    std::vector<VkQueueFamilyProperties> queue_families(queue_family_count);
    vkGetPhysicalDeviceQueueFamilyProperties(device, &queue_family_count, queue_families.data());

    for (uint32_t i = 0; i < queue_families.size(); i++) {
        if (queue_families[i].queueFlags & VK_QUEUE_GRAPHICS_BIT) {
            indices.graphics_family = i;
        }

        if (queue_families[i].queueFlags & VK_QUEUE_COMPUTE_BIT) {
            indices.compute_family = i;
        }

        if (surface_ != VK_NULL_HANDLE) {
            VkBool32 present_support = false;
            vkGetPhysicalDeviceSurfaceSupportKHR(device, i, surface_, &present_support);
            if (present_support) {
                indices.present_family = i;
            }
        } else {
            // For headless rendering, use graphics queue for present
            indices.present_family = indices.graphics_family;
        }

        if (indices.is_complete()) {
            break;
        }
    }

    return indices;
}

bool GraphicsDevice::check_device_extension_support(VkPhysicalDevice device) {
    uint32_t extension_count;
    vkEnumerateDeviceExtensionProperties(device, nullptr, &extension_count, nullptr);

    std::vector<VkExtensionProperties> available_extensions(extension_count);
    vkEnumerateDeviceExtensionProperties(device, nullptr, &extension_count,
                                        available_extensions.data());

    std::set<std::string> required_extensions(DEVICE_EXTENSIONS.begin(),
                                              DEVICE_EXTENSIONS.end());

    for (const auto& extension : available_extensions) {
        required_extensions.erase(extension.extensionName);
    }

    return required_extensions.empty();
}

SwapchainSupportDetails GraphicsDevice::query_swapchain_support(VkPhysicalDevice device) {
    SwapchainSupportDetails details;

    if (surface_ != VK_NULL_HANDLE) {
        vkGetPhysicalDeviceSurfaceCapabilitiesKHR(device, surface_, &details.capabilities);

        uint32_t format_count;
        vkGetPhysicalDeviceSurfaceFormatsKHR(device, surface_, &format_count, nullptr);
        if (format_count != 0) {
            details.formats.resize(format_count);
            vkGetPhysicalDeviceSurfaceFormatsKHR(device, surface_, &format_count,
                                                details.formats.data());
        }

        uint32_t present_mode_count;
        vkGetPhysicalDeviceSurfacePresentModesKHR(device, surface_, &present_mode_count, nullptr);
        if (present_mode_count != 0) {
            details.present_modes.resize(present_mode_count);
            vkGetPhysicalDeviceSurfacePresentModesKHR(device, surface_, &present_mode_count,
                                                     details.present_modes.data());
        }
    }

    return details;
}

uint32_t GraphicsDevice::find_memory_type(uint32_t type_filter,
                                          VkMemoryPropertyFlags properties) {
    VkPhysicalDeviceMemoryProperties mem_properties;
    vkGetPhysicalDeviceMemoryProperties(physical_device_, &mem_properties);

    for (uint32_t i = 0; i < mem_properties.memoryTypeCount; i++) {
        if ((type_filter & (1 << i)) &&
            (mem_properties.memoryTypes[i].propertyFlags & properties) == properties) {
            return i;
        }
    }

    throw std::runtime_error("Failed to find suitable memory type");
}

std::vector<const char*> GraphicsDevice::get_required_extensions(bool enable_validation) {
    std::vector<const char*> extensions;

    // Add surface extensions if needed
    if (surface_ != VK_NULL_HANDLE) {
        extensions.push_back(VK_KHR_SURFACE_EXTENSION_NAME);
#ifdef __linux__
        extensions.push_back("VK_KHR_xcb_surface");
#elif _WIN32
        extensions.push_back("VK_KHR_win32_surface");
#elif __APPLE__
        extensions.push_back("VK_EXT_metal_surface");
#endif
    }

    if (enable_validation) {
        extensions.push_back(VK_EXT_DEBUG_UTILS_EXTENSION_NAME);
    }

    return extensions;
}

bool GraphicsDevice::check_validation_layer_support() {
    uint32_t layer_count;
    vkEnumerateInstanceLayerProperties(&layer_count, nullptr);

    std::vector<VkLayerProperties> available_layers(layer_count);
    vkEnumerateInstanceLayerProperties(&layer_count, available_layers.data());

    for (const char* layer_name : VALIDATION_LAYERS) {
        bool found = false;
        for (const auto& layer_props : available_layers) {
            if (strcmp(layer_name, layer_props.layerName) == 0) {
                found = true;
                break;
            }
        }
        if (!found) {
            return false;
        }
    }

    return true;
}

// ============================================================================
// Resource Management
// ============================================================================

GPUBuffer GraphicsDevice::create_buffer(VkDeviceSize size, VkBufferUsageFlags usage,
                                       VkMemoryPropertyFlags properties) {
    GPUBuffer buffer;
    buffer.size = size;
    buffer.usage = usage;

    VkBufferCreateInfo buffer_info{};
    buffer_info.sType = VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO;
    buffer_info.size = size;
    buffer_info.usage = usage;
    buffer_info.sharingMode = VK_SHARING_MODE_EXCLUSIVE;

    VkResult result = vkCreateBuffer(device_, &buffer_info, nullptr, &buffer.buffer);
    if (result != VK_SUCCESS) {
        throw std::runtime_error("Failed to create buffer");
    }

    VkMemoryRequirements mem_requirements;
    vkGetBufferMemoryRequirements(device_, buffer.buffer, &mem_requirements);

    VkMemoryAllocateInfo alloc_info{};
    alloc_info.sType = VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO;
    alloc_info.allocationSize = mem_requirements.size;
    alloc_info.memoryTypeIndex = find_memory_type(mem_requirements.memoryTypeBits, properties);

    result = vkAllocateMemory(device_, &alloc_info, nullptr, &buffer.memory);
    if (result != VK_SUCCESS) {
        vkDestroyBuffer(device_, buffer.buffer, nullptr);
        throw std::runtime_error("Failed to allocate buffer memory");
    }

    vkBindBufferMemory(device_, buffer.buffer, buffer.memory, 0);

    return buffer;
}

void GraphicsDevice::destroy_buffer(GPUBuffer& buffer) {
    if (buffer.mapped) {
        vkUnmapMemory(device_, buffer.memory);
        buffer.mapped = nullptr;
    }
    if (buffer.buffer != VK_NULL_HANDLE) {
        vkDestroyBuffer(device_, buffer.buffer, nullptr);
        buffer.buffer = VK_NULL_HANDLE;
    }
    if (buffer.memory != VK_NULL_HANDLE) {
        vkFreeMemory(device_, buffer.memory, nullptr);
        buffer.memory = VK_NULL_HANDLE;
    }
}

GPUImage GraphicsDevice::create_image(uint32_t width, uint32_t height, VkFormat format,
                                     VkImageUsageFlags usage, uint32_t mip_levels) {
    GPUImage image;
    image.format = format;
    image.extent = {width, height};
    image.mip_levels = mip_levels;

    VkImageCreateInfo image_info{};
    image_info.sType = VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO;
    image_info.imageType = VK_IMAGE_TYPE_2D;
    image_info.extent.width = width;
    image_info.extent.height = height;
    image_info.extent.depth = 1;
    image_info.mipLevels = mip_levels;
    image_info.arrayLayers = 1;
    image_info.format = format;
    image_info.tiling = VK_IMAGE_TILING_OPTIMAL;
    image_info.initialLayout = VK_IMAGE_LAYOUT_UNDEFINED;
    image_info.usage = usage;
    image_info.sharingMode = VK_SHARING_MODE_EXCLUSIVE;
    image_info.samples = VK_SAMPLE_COUNT_1_BIT;

    VkResult result = vkCreateImage(device_, &image_info, nullptr, &image.image);
    if (result != VK_SUCCESS) {
        throw std::runtime_error("Failed to create image");
    }

    VkMemoryRequirements mem_requirements;
    vkGetImageMemoryRequirements(device_, image.image, &mem_requirements);

    VkMemoryAllocateInfo alloc_info{};
    alloc_info.sType = VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO;
    alloc_info.allocationSize = mem_requirements.size;
    alloc_info.memoryTypeIndex = find_memory_type(mem_requirements.memoryTypeBits,
                                                  VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT);

    result = vkAllocateMemory(device_, &alloc_info, nullptr, &image.memory);
    if (result != VK_SUCCESS) {
        vkDestroyImage(device_, image.image, nullptr);
        throw std::runtime_error("Failed to allocate image memory");
    }

    vkBindImageMemory(device_, image.image, image.memory, 0);

    // Create image view
    VkImageViewCreateInfo view_info{};
    view_info.sType = VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO;
    view_info.image = image.image;
    view_info.viewType = VK_IMAGE_VIEW_TYPE_2D;
    view_info.format = format;
    view_info.subresourceRange.aspectMask = (format == VK_FORMAT_D32_SFLOAT ||
                                             format == VK_FORMAT_D24_UNORM_S8_UINT)
                                           ? VK_IMAGE_ASPECT_DEPTH_BIT
                                           : VK_IMAGE_ASPECT_COLOR_BIT;
    view_info.subresourceRange.baseMipLevel = 0;
    view_info.subresourceRange.levelCount = mip_levels;
    view_info.subresourceRange.baseArrayLayer = 0;
    view_info.subresourceRange.layerCount = 1;

    result = vkCreateImageView(device_, &view_info, nullptr, &image.view);
    if (result != VK_SUCCESS) {
        vkDestroyImage(device_, image.image, nullptr);
        vkFreeMemory(device_, image.memory, nullptr);
        throw std::runtime_error("Failed to create image view");
    }

    return image;
}

void GraphicsDevice::destroy_image(GPUImage& image) {
    if (image.sampler != VK_NULL_HANDLE) {
        vkDestroySampler(device_, image.sampler, nullptr);
        image.sampler = VK_NULL_HANDLE;
    }
    if (image.view != VK_NULL_HANDLE) {
        vkDestroyImageView(device_, image.view, nullptr);
        image.view = VK_NULL_HANDLE;
    }
    if (image.image != VK_NULL_HANDLE) {
        vkDestroyImage(device_, image.image, nullptr);
        image.image = VK_NULL_HANDLE;
    }
    if (image.memory != VK_NULL_HANDLE) {
        vkFreeMemory(device_, image.memory, nullptr);
        image.memory = VK_NULL_HANDLE;
    }
}

GPUMesh GraphicsDevice::upload_mesh(const props::Mesh& mesh) {
    // DEBUG: Validate mesh before upload
    std::cout << "=== MESH UPLOAD ===" << std::endl;
    std::cout << "Vertices: " << mesh.vertices.size() << std::endl;
    std::cout << "Normals: " << mesh.normals.size() << std::endl;
    std::cout << "Colors: " << mesh.colors.size() << std::endl;
    std::cout << "Indices: " << mesh.indices.size() << std::endl;

    if (mesh.vertices.empty()) {
        std::cout << "ERROR: Mesh has no vertices!" << std::endl;
        return GPUMesh{};
    }

    if (mesh.indices.empty()) {
        std::cout << "ERROR: Mesh has no indices!" << std::endl;
        return GPUMesh{};
    }

    if (mesh.normals.size() != mesh.vertices.size()) {
        std::cout << "WARNING: Normal count mismatch! Vertices: "
                  << mesh.vertices.size() << ", Normals: " << mesh.normals.size() << std::endl;
    }

    // Log color info
    if (mesh.colors.empty()) {
        std::cout << "WARNING: Mesh has no vertex colors - will use height-based fallback" << std::endl;
    } else {
        std::cout << "Using " << mesh.colors.size() << " vertex colors from mesh" << std::endl;
        if (mesh.colors.size() > 0) {
            std::cout << "  Sample color[0]: R=" << mesh.colors[0].x 
                      << ", G=" << mesh.colors[0].y << ", B=" << mesh.colors[0].z << std::endl;
        }
        if (mesh.colors.size() > 500) {
            std::cout << "  Sample color[500]: R=" << mesh.colors[500].x 
                      << ", G=" << mesh.colors[500].y << ", B=" << mesh.colors[500].z << std::endl;
        }
    }

    // Log bounding box
    float minX = 1e10f, maxX = -1e10f;
    float minY = 1e10f, maxY = -1e10f;
    float minZ = 1e10f, maxZ = -1e10f;
    for (const auto& v : mesh.vertices) {
        minX = std::min(minX, v.x); maxX = std::max(maxX, v.x);
        minY = std::min(minY, v.y); maxY = std::max(maxY, v.y);
        minZ = std::min(minZ, v.z); maxZ = std::max(maxZ, v.z);
    }
    std::cout << "Bounding box: (" << minX << "," << minY << "," << minZ << ") to ("
              << maxX << "," << maxY << "," << maxZ << ")" << std::endl;
    std::cout << "==================" << std::endl;

    GPUMesh gpu_mesh;
    gpu_mesh.vertex_count = static_cast<uint32_t>(mesh.vertices.size());
    gpu_mesh.index_count = static_cast<uint32_t>(mesh.indices.size());

    // Interleave vertex data (position + normal + uv + color)
    std::vector<graphics::Vertex> vertices(mesh.vertices.size());
    for (size_t i = 0; i < mesh.vertices.size(); ++i) {
        vertices[i].position[0] = mesh.vertices[i].x;
        vertices[i].position[1] = mesh.vertices[i].y;
        vertices[i].position[2] = mesh.vertices[i].z;
        vertices[i].normal[0] = mesh.normals[i].x;
        vertices[i].normal[1] = mesh.normals[i].y;
        vertices[i].normal[2] = mesh.normals[i].z;
        // Generate UVs from position (simple planar mapping)
        vertices[i].uv[0] = mesh.vertices[i].x * 0.1f;
        vertices[i].uv[1] = mesh.vertices[i].z * 0.1f;
        
        // Use vertex colors if available, otherwise default to white
        if (i < mesh.colors.size()) {
            vertices[i].color[0] = mesh.colors[i].x;
            vertices[i].color[1] = mesh.colors[i].y;
            vertices[i].color[2] = mesh.colors[i].z;
            vertices[i].color[3] = 1.0f;
        } else {
            // Default: derive color from height for visual interest
            float height_normalized = (mesh.vertices[i].y + 50.0f) / 100.0f;
            height_normalized = std::clamp(height_normalized, 0.0f, 1.0f);
            // Gradient from dark green (low) to white (high) via brown
            if (height_normalized < 0.3f) {
                // Water/low: blue-green
                vertices[i].color[0] = 0.1f;
                vertices[i].color[1] = 0.3f + height_normalized;
                vertices[i].color[2] = 0.4f;
            } else if (height_normalized < 0.6f) {
                // Mid: green to brown
                float t = (height_normalized - 0.3f) / 0.3f;
                vertices[i].color[0] = 0.2f + t * 0.3f;
                vertices[i].color[1] = 0.5f - t * 0.2f;
                vertices[i].color[2] = 0.1f;
            } else {
                // High: brown to white (snow)
                float t = (height_normalized - 0.6f) / 0.4f;
                vertices[i].color[0] = 0.5f + t * 0.5f;
                vertices[i].color[1] = 0.3f + t * 0.7f;
                vertices[i].color[2] = 0.1f + t * 0.9f;
            }
            vertices[i].color[3] = 1.0f;
        }
    }

    VkDeviceSize vertex_buffer_size = sizeof(graphics::Vertex) * vertices.size();
    VkDeviceSize index_buffer_size = sizeof(uint32_t) * mesh.indices.size();

    // Create staging buffers
    GPUBuffer vertex_staging = create_buffer(
        vertex_buffer_size,
        VK_BUFFER_USAGE_TRANSFER_SRC_BIT,
        VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT
    );

    GPUBuffer index_staging = create_buffer(
        index_buffer_size,
        VK_BUFFER_USAGE_TRANSFER_SRC_BIT,
        VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT
    );

    // Copy data to staging buffers
    void* data;
    VkResult map_result = vkMapMemory(device_, vertex_staging.memory, 0, vertex_buffer_size, 0, &data);
    if (map_result != VK_SUCCESS) {
        destroy_buffer(vertex_staging);
        destroy_buffer(index_staging);
        throw std::runtime_error("Failed to map vertex staging buffer memory");
    }
    std::memcpy(data, vertices.data(), vertex_buffer_size);
    vkUnmapMemory(device_, vertex_staging.memory);

    map_result = vkMapMemory(device_, index_staging.memory, 0, index_buffer_size, 0, &data);
    if (map_result != VK_SUCCESS) {
        destroy_buffer(vertex_staging);
        destroy_buffer(index_staging);
        throw std::runtime_error("Failed to map index staging buffer memory");
    }
    std::memcpy(data, mesh.indices.data(), index_buffer_size);
    vkUnmapMemory(device_, index_staging.memory);

    // Create device-local buffers with exception safety for staging cleanup
    try {
        gpu_mesh.vertex_buffer = create_buffer(
            vertex_buffer_size,
            VK_BUFFER_USAGE_TRANSFER_DST_BIT | VK_BUFFER_USAGE_VERTEX_BUFFER_BIT,
            VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT
        );

        gpu_mesh.index_buffer = create_buffer(
            index_buffer_size,
            VK_BUFFER_USAGE_TRANSFER_DST_BIT | VK_BUFFER_USAGE_INDEX_BUFFER_BIT,
            VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT
        );
    } catch (...) {
        destroy_buffer(vertex_staging);
        destroy_buffer(index_staging);
        if (gpu_mesh.vertex_buffer.is_valid()) {
            destroy_buffer(gpu_mesh.vertex_buffer);
        }
        throw;
    }

    // Copy from staging to device-local
    VkCommandBuffer cmd = begin_single_time_commands();

    VkBufferCopy vertex_copy{};
    vertex_copy.size = vertex_buffer_size;
    vkCmdCopyBuffer(cmd, vertex_staging.buffer, gpu_mesh.vertex_buffer.buffer, 1, &vertex_copy);

    VkBufferCopy index_copy{};
    index_copy.size = index_buffer_size;
    vkCmdCopyBuffer(cmd, index_staging.buffer, gpu_mesh.index_buffer.buffer, 1, &index_copy);

    end_single_time_commands(cmd);

    // Cleanup staging buffers
    destroy_buffer(vertex_staging);
    destroy_buffer(index_staging);

    return gpu_mesh;
}

void GraphicsDevice::destroy_mesh(GPUMesh& gpu_mesh) {
    destroy_buffer(gpu_mesh.vertex_buffer);
    destroy_buffer(gpu_mesh.index_buffer);
    gpu_mesh.vertex_count = 0;
    gpu_mesh.index_count = 0;
}

void* GraphicsDevice::map_buffer(GPUBuffer& buffer) {
    if (buffer.mapped == nullptr) {
        VkResult result = vkMapMemory(device_, buffer.memory, 0, buffer.size, 0, &buffer.mapped);
        if (result != VK_SUCCESS) {
            buffer.mapped = nullptr;
            throw std::runtime_error("Failed to map buffer memory");
        }
    }
    return buffer.mapped;
}

void GraphicsDevice::unmap_buffer(GPUBuffer& buffer) {
    if (buffer.mapped != nullptr) {
        vkUnmapMemory(device_, buffer.memory);
        buffer.mapped = nullptr;
    }
}

void GraphicsDevice::update_buffer(GPUBuffer& buffer, const void* data, VkDeviceSize size) {
    void* mapped = map_buffer(buffer);
    std::memcpy(mapped, data, size);
    unmap_buffer(buffer);
}

VkCommandBuffer GraphicsDevice::begin_single_time_commands() {
    VkCommandBufferAllocateInfo alloc_info{};
    alloc_info.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO;
    alloc_info.level = VK_COMMAND_BUFFER_LEVEL_PRIMARY;
    alloc_info.commandPool = command_pool_;
    alloc_info.commandBufferCount = 1;

    VkCommandBuffer command_buffer;
    vkAllocateCommandBuffers(device_, &alloc_info, &command_buffer);

    VkCommandBufferBeginInfo begin_info{};
    begin_info.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO;
    begin_info.flags = VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT;

    vkBeginCommandBuffer(command_buffer, &begin_info);

    return command_buffer;
}

void GraphicsDevice::end_single_time_commands(VkCommandBuffer command_buffer) {
    vkEndCommandBuffer(command_buffer);

    VkSubmitInfo submit_info{};
    submit_info.sType = VK_STRUCTURE_TYPE_SUBMIT_INFO;
    submit_info.commandBufferCount = 1;
    submit_info.pCommandBuffers = &command_buffer;

    vkQueueSubmit(graphics_queue_, 1, &submit_info, VK_NULL_HANDLE);
    vkQueueWaitIdle(graphics_queue_);

    vkFreeCommandBuffers(device_, command_pool_, 1, &command_buffer);
}

// ============================================================================
// Shader Management
// ============================================================================

ShaderModule GraphicsDevice::create_shader_module(const std::vector<uint32_t>& spirv_code,
                                                  VkShaderStageFlagBits stage) {
    ShaderModule shader;
    shader.stage = stage;
    shader.spirv_code = spirv_code;

    VkShaderModuleCreateInfo create_info{};
    create_info.sType = VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO;
    create_info.codeSize = spirv_code.size() * sizeof(uint32_t);
    create_info.pCode = spirv_code.data();

    VkResult result = vkCreateShaderModule(device_, &create_info, nullptr, &shader.module);
    if (result != VK_SUCCESS) {
        throw std::runtime_error("Failed to create shader module");
    }

    return shader;
}

void GraphicsDevice::destroy_shader_module(ShaderModule& shader) {
    if (shader.module != VK_NULL_HANDLE) {
        vkDestroyShaderModule(device_, shader.module, nullptr);
        shader.module = VK_NULL_HANDLE;
    }
}

// ============================================================================
// Pipeline Management
// ============================================================================

Pipeline GraphicsDevice::create_pipeline(const PipelineConfig& config, VkRenderPass render_pass,
                                         const std::vector<uint32_t>& vertex_spirv,
                                         const std::vector<uint32_t>& fragment_spirv) {
    Pipeline pipeline;

    // Create shader modules
    pipeline.vertex_shader = create_shader_module(vertex_spirv, VK_SHADER_STAGE_VERTEX_BIT);
    pipeline.fragment_shader = create_shader_module(fragment_spirv, VK_SHADER_STAGE_FRAGMENT_BIT);

    if (!pipeline.vertex_shader.is_valid() || !pipeline.fragment_shader.is_valid()) {
        std::cerr << "Failed to create shader modules" << std::endl;
        return pipeline;
    }

    // Shader stages
    VkPipelineShaderStageCreateInfo shader_stages[2] = {};
    shader_stages[0].sType = VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO;
    shader_stages[0].stage = VK_SHADER_STAGE_VERTEX_BIT;
    shader_stages[0].module = pipeline.vertex_shader.module;
    shader_stages[0].pName = "main";
    
    shader_stages[1].sType = VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO;
    shader_stages[1].stage = VK_SHADER_STAGE_FRAGMENT_BIT;
    shader_stages[1].module = pipeline.fragment_shader.module;
    shader_stages[1].pName = "main";

    // Vertex input
    auto binding_desc = graphics::Vertex::get_binding_description();
    auto attr_descs = graphics::Vertex::get_attribute_descriptions();

    VkPipelineVertexInputStateCreateInfo vertex_input_info{};
    vertex_input_info.sType = VK_STRUCTURE_TYPE_PIPELINE_VERTEX_INPUT_STATE_CREATE_INFO;
    vertex_input_info.vertexBindingDescriptionCount = 1;
    vertex_input_info.pVertexBindingDescriptions = &binding_desc;
    vertex_input_info.vertexAttributeDescriptionCount = static_cast<uint32_t>(attr_descs.size());
    vertex_input_info.pVertexAttributeDescriptions = attr_descs.data();

    // Input assembly
    VkPipelineInputAssemblyStateCreateInfo input_assembly{};
    input_assembly.sType = VK_STRUCTURE_TYPE_PIPELINE_INPUT_ASSEMBLY_STATE_CREATE_INFO;
    input_assembly.topology = config.topology;
    input_assembly.primitiveRestartEnable = VK_FALSE;

    // Viewport state (dynamic)
    VkPipelineViewportStateCreateInfo viewport_state{};
    viewport_state.sType = VK_STRUCTURE_TYPE_PIPELINE_VIEWPORT_STATE_CREATE_INFO;
    viewport_state.viewportCount = 1;
    viewport_state.scissorCount = 1;

    // Rasterizer
    VkPipelineRasterizationStateCreateInfo rasterizer{};
    rasterizer.sType = VK_STRUCTURE_TYPE_PIPELINE_RASTERIZATION_STATE_CREATE_INFO;
    rasterizer.depthClampEnable = VK_FALSE;
    rasterizer.rasterizerDiscardEnable = VK_FALSE;
    rasterizer.polygonMode = config.polygon_mode;
    rasterizer.lineWidth = 1.0f;
    rasterizer.cullMode = VK_CULL_MODE_NONE;  // Disable culling until rendering confirmed
    rasterizer.frontFace = VK_FRONT_FACE_COUNTER_CLOCKWISE;
    rasterizer.depthBiasEnable = VK_FALSE;

    // Multisampling
    VkPipelineMultisampleStateCreateInfo multisampling{};
    multisampling.sType = VK_STRUCTURE_TYPE_PIPELINE_MULTISAMPLE_STATE_CREATE_INFO;
    multisampling.sampleShadingEnable = VK_FALSE;
    multisampling.rasterizationSamples = VK_SAMPLE_COUNT_1_BIT;

    // Depth stencil
    VkPipelineDepthStencilStateCreateInfo depth_stencil{};
    depth_stencil.sType = VK_STRUCTURE_TYPE_PIPELINE_DEPTH_STENCIL_STATE_CREATE_INFO;
    depth_stencil.depthTestEnable = config.depth_test ? VK_TRUE : VK_FALSE;
    depth_stencil.depthWriteEnable = config.depth_write ? VK_TRUE : VK_FALSE;
    depth_stencil.depthCompareOp = VK_COMPARE_OP_LESS_OR_EQUAL;  // Fixed depth compare for proper depth test
    depth_stencil.depthBoundsTestEnable = VK_FALSE;
    depth_stencil.stencilTestEnable = VK_FALSE;

    // Color blending
    VkPipelineColorBlendAttachmentState color_blend_attachment{};
    color_blend_attachment.colorWriteMask = VK_COLOR_COMPONENT_R_BIT | VK_COLOR_COMPONENT_G_BIT |
                                           VK_COLOR_COMPONENT_B_BIT | VK_COLOR_COMPONENT_A_BIT;
    color_blend_attachment.blendEnable = config.blend_enable ? VK_TRUE : VK_FALSE;
    color_blend_attachment.srcColorBlendFactor = config.src_blend;
    color_blend_attachment.dstColorBlendFactor = config.dst_blend;
    color_blend_attachment.colorBlendOp = VK_BLEND_OP_ADD;
    color_blend_attachment.srcAlphaBlendFactor = VK_BLEND_FACTOR_ONE;
    color_blend_attachment.dstAlphaBlendFactor = VK_BLEND_FACTOR_ZERO;
    color_blend_attachment.alphaBlendOp = VK_BLEND_OP_ADD;

    VkPipelineColorBlendStateCreateInfo color_blending{};
    color_blending.sType = VK_STRUCTURE_TYPE_PIPELINE_COLOR_BLEND_STATE_CREATE_INFO;
    color_blending.logicOpEnable = VK_FALSE;
    color_blending.attachmentCount = 1;
    color_blending.pAttachments = &color_blend_attachment;

    // Dynamic state
    std::vector<VkDynamicState> dynamic_states = {
        VK_DYNAMIC_STATE_VIEWPORT,
        VK_DYNAMIC_STATE_SCISSOR
    };

    VkPipelineDynamicStateCreateInfo dynamic_state{};
    dynamic_state.sType = VK_STRUCTURE_TYPE_PIPELINE_DYNAMIC_STATE_CREATE_INFO;
    dynamic_state.dynamicStateCount = static_cast<uint32_t>(dynamic_states.size());
    dynamic_state.pDynamicStates = dynamic_states.data();

    // Descriptor set layout - frame uniforms binding
    VkDescriptorSetLayoutBinding ubo_binding{};
    ubo_binding.binding = 0;
    ubo_binding.descriptorType = VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER;
    ubo_binding.descriptorCount = 1;
    ubo_binding.stageFlags = VK_SHADER_STAGE_VERTEX_BIT | VK_SHADER_STAGE_FRAGMENT_BIT;

    VkDescriptorSetLayoutCreateInfo layout_info{};
    layout_info.sType = VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO;
    layout_info.bindingCount = 1;
    layout_info.pBindings = &ubo_binding;

    VkResult result = vkCreateDescriptorSetLayout(device_, &layout_info, nullptr, 
                                                  &pipeline.descriptor_layout);
    if (result != VK_SUCCESS) {
        std::cerr << "Failed to create descriptor set layout: " << result << std::endl;
        destroy_shader_module(pipeline.vertex_shader);
        destroy_shader_module(pipeline.fragment_shader);
        return pipeline;
    }

    // Push constants for per-draw transforms
    VkPushConstantRange push_constant_range{};
    push_constant_range.stageFlags = VK_SHADER_STAGE_VERTEX_BIT | VK_SHADER_STAGE_FRAGMENT_BIT;
    push_constant_range.offset = 0;
    push_constant_range.size = sizeof(graphics::PushConstants);

    // Pipeline layout
    VkPipelineLayoutCreateInfo pipeline_layout_info{};
    pipeline_layout_info.sType = VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO;
    pipeline_layout_info.setLayoutCount = 1;
    pipeline_layout_info.pSetLayouts = &pipeline.descriptor_layout;
    pipeline_layout_info.pushConstantRangeCount = 1;
    pipeline_layout_info.pPushConstantRanges = &push_constant_range;

    result = vkCreatePipelineLayout(device_, &pipeline_layout_info, nullptr, &pipeline.layout);
    if (result != VK_SUCCESS) {
        std::cerr << "Failed to create pipeline layout: " << result << std::endl;
        vkDestroyDescriptorSetLayout(device_, pipeline.descriptor_layout, nullptr);
        destroy_shader_module(pipeline.vertex_shader);
        destroy_shader_module(pipeline.fragment_shader);
        pipeline.descriptor_layout = VK_NULL_HANDLE;
        return pipeline;
    }

    // Create graphics pipeline
    VkGraphicsPipelineCreateInfo pipeline_info{};
    pipeline_info.sType = VK_STRUCTURE_TYPE_GRAPHICS_PIPELINE_CREATE_INFO;
    pipeline_info.stageCount = 2;
    pipeline_info.pStages = shader_stages;
    pipeline_info.pVertexInputState = &vertex_input_info;
    pipeline_info.pInputAssemblyState = &input_assembly;
    pipeline_info.pViewportState = &viewport_state;
    pipeline_info.pRasterizationState = &rasterizer;
    pipeline_info.pMultisampleState = &multisampling;
    pipeline_info.pDepthStencilState = &depth_stencil;
    pipeline_info.pColorBlendState = &color_blending;
    pipeline_info.pDynamicState = &dynamic_state;
    pipeline_info.layout = pipeline.layout;
    pipeline_info.renderPass = render_pass;
    pipeline_info.subpass = 0;
    pipeline_info.basePipelineHandle = VK_NULL_HANDLE;

    result = vkCreateGraphicsPipelines(device_, VK_NULL_HANDLE, 1, &pipeline_info, 
                                      nullptr, &pipeline.pipeline);
    if (result != VK_SUCCESS) {
        std::cerr << "Failed to create graphics pipeline: " << result << std::endl;
        vkDestroyPipelineLayout(device_, pipeline.layout, nullptr);
        vkDestroyDescriptorSetLayout(device_, pipeline.descriptor_layout, nullptr);
        destroy_shader_module(pipeline.vertex_shader);
        destroy_shader_module(pipeline.fragment_shader);
        pipeline.layout = VK_NULL_HANDLE;
        pipeline.descriptor_layout = VK_NULL_HANDLE;
        return pipeline;
    }

    // Compute hash from shader code
    uint64_t hash_val = 0;
    for (uint32_t v : vertex_spirv) hash_val ^= v + 0x9e3779b9 + (hash_val << 6) + (hash_val >> 2);
    for (uint32_t v : fragment_spirv) hash_val ^= v + 0x9e3779b9 + (hash_val << 6) + (hash_val >> 2);
    pipeline.hash = hash_val;

    return pipeline;
}

void GraphicsDevice::destroy_pipeline(Pipeline& pipeline) {
    if (pipeline.pipeline != VK_NULL_HANDLE) {
        vkDestroyPipeline(device_, pipeline.pipeline, nullptr);
        pipeline.pipeline = VK_NULL_HANDLE;
    }
    if (pipeline.layout != VK_NULL_HANDLE) {
        vkDestroyPipelineLayout(device_, pipeline.layout, nullptr);
        pipeline.layout = VK_NULL_HANDLE;
    }
    if (pipeline.descriptor_layout != VK_NULL_HANDLE) {
        vkDestroyDescriptorSetLayout(device_, pipeline.descriptor_layout, nullptr);
        pipeline.descriptor_layout = VK_NULL_HANDLE;
    }
    if (pipeline.vertex_shader.is_valid()) {
        destroy_shader_module(pipeline.vertex_shader);
    }
    if (pipeline.fragment_shader.is_valid()) {
        destroy_shader_module(pipeline.fragment_shader);
    }
}

// ============================================================================
// Swapchain Management
// ============================================================================

VkSurfaceFormatKHR GraphicsDevice::choose_swap_surface_format(
    const std::vector<VkSurfaceFormatKHR>& formats) {
    for (const auto& format : formats) {
        if (format.format == VK_FORMAT_B8G8R8A8_SRGB && 
            format.colorSpace == VK_COLOR_SPACE_SRGB_NONLINEAR_KHR) {
            return format;
        }
    }
    return formats[0];
}

VkPresentModeKHR GraphicsDevice::choose_swap_present_mode(
    const std::vector<VkPresentModeKHR>& modes) {
    // If vsync is enabled, prefer FIFO (vsync) over MAILBOX
    // If vsync is disabled, prefer MAILBOX (triple buffering, no vsync) over FIFO
    if (enable_vsync_) {
        // Always use FIFO when vsync enabled - it's guaranteed to be available
        return VK_PRESENT_MODE_FIFO_KHR;
    } else {
        // Try to use MAILBOX for lowest latency without vsync
        for (const auto& mode : modes) {
            if (mode == VK_PRESENT_MODE_MAILBOX_KHR) {
                return mode;  // Triple buffering, no vsync
            }
        }
        // Fall back to FIFO if MAILBOX not available
        return VK_PRESENT_MODE_FIFO_KHR;
    }
}

VkExtent2D GraphicsDevice::choose_swap_extent(const VkSurfaceCapabilitiesKHR& capabilities,
                                              uint32_t width, uint32_t height) {
    if (capabilities.currentExtent.width != UINT32_MAX) {
        return capabilities.currentExtent;
    }
    
    VkExtent2D extent = {width, height};
    extent.width = std::max(capabilities.minImageExtent.width,
                           std::min(capabilities.maxImageExtent.width, extent.width));
    extent.height = std::max(capabilities.minImageExtent.height,
                            std::min(capabilities.maxImageExtent.height, extent.height));
    return extent;
}

bool GraphicsDevice::create_swapchain(uint32_t width, uint32_t height) {
    if (surface_ == VK_NULL_HANDLE) {
        std::cerr << "Cannot create swapchain without surface" << std::endl;
        return false;
    }

    SwapchainSupportDetails support = query_swapchain_support(physical_device_);
    VkSurfaceFormatKHR surface_format = choose_swap_surface_format(support.formats);
    VkPresentModeKHR present_mode = choose_swap_present_mode(support.present_modes);
    VkExtent2D extent = choose_swap_extent(support.capabilities, width, height);

    uint32_t image_count = support.capabilities.minImageCount + 1;
    if (support.capabilities.maxImageCount > 0 && 
        image_count > support.capabilities.maxImageCount) {
        image_count = support.capabilities.maxImageCount;
    }

    VkSwapchainCreateInfoKHR create_info{};
    create_info.sType = VK_STRUCTURE_TYPE_SWAPCHAIN_CREATE_INFO_KHR;
    create_info.surface = surface_;
    create_info.minImageCount = image_count;
    create_info.imageFormat = surface_format.format;
    create_info.imageColorSpace = surface_format.colorSpace;
    create_info.imageExtent = extent;
    create_info.imageArrayLayers = 1;
    create_info.imageUsage = VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT;

    uint32_t queue_family_indices[] = {
        queue_families_.graphics_family.value(),
        queue_families_.present_family.value()
    };

    if (queue_families_.graphics_family != queue_families_.present_family) {
        create_info.imageSharingMode = VK_SHARING_MODE_CONCURRENT;
        create_info.queueFamilyIndexCount = 2;
        create_info.pQueueFamilyIndices = queue_family_indices;
    } else {
        create_info.imageSharingMode = VK_SHARING_MODE_EXCLUSIVE;
    }

    create_info.preTransform = support.capabilities.currentTransform;
    create_info.compositeAlpha = VK_COMPOSITE_ALPHA_OPAQUE_BIT_KHR;
    create_info.presentMode = present_mode;
    create_info.clipped = VK_TRUE;
    create_info.oldSwapchain = swapchain_;

    VkResult result = vkCreateSwapchainKHR(device_, &create_info, nullptr, &swapchain_);
    if (result != VK_SUCCESS) {
        std::cerr << "Failed to create swapchain: " << result << std::endl;
        return false;
    }

    // Destroy old swapchain if it existed
    if (create_info.oldSwapchain != VK_NULL_HANDLE) {
        for (auto view : swapchain_image_views_) {
            vkDestroyImageView(device_, view, nullptr);
        }
        vkDestroySwapchainKHR(device_, create_info.oldSwapchain, nullptr);
    }

    swapchain_format_ = surface_format.format;
    swapchain_extent_ = extent;

    // Get swapchain images
    vkGetSwapchainImagesKHR(device_, swapchain_, &image_count, nullptr);
    swapchain_images_.resize(image_count);
    vkGetSwapchainImagesKHR(device_, swapchain_, &image_count, swapchain_images_.data());

    // Create image views
    swapchain_image_views_.resize(image_count);
    for (uint32_t i = 0; i < image_count; i++) {
        VkImageViewCreateInfo view_info{};
        view_info.sType = VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO;
        view_info.image = swapchain_images_[i];
        view_info.viewType = VK_IMAGE_VIEW_TYPE_2D;
        view_info.format = swapchain_format_;
        view_info.components.r = VK_COMPONENT_SWIZZLE_IDENTITY;
        view_info.components.g = VK_COMPONENT_SWIZZLE_IDENTITY;
        view_info.components.b = VK_COMPONENT_SWIZZLE_IDENTITY;
        view_info.components.a = VK_COMPONENT_SWIZZLE_IDENTITY;
        view_info.subresourceRange.aspectMask = VK_IMAGE_ASPECT_COLOR_BIT;
        view_info.subresourceRange.baseMipLevel = 0;
        view_info.subresourceRange.levelCount = 1;
        view_info.subresourceRange.baseArrayLayer = 0;
        view_info.subresourceRange.layerCount = 1;

        result = vkCreateImageView(device_, &view_info, nullptr, &swapchain_image_views_[i]);
        if (result != VK_SUCCESS) {
            std::cerr << "Failed to create swapchain image view: " << result << std::endl;
            return false;
        }
    }

    std::cout << "Created swapchain: " << extent.width << "x" << extent.height 
              << " with " << image_count << " images" << std::endl;
    return true;
}

bool GraphicsDevice::recreate_swapchain(uint32_t width, uint32_t height) {
    vkDeviceWaitIdle(device_);
    return create_swapchain(width, height);
}

void GraphicsDevice::cleanup_swapchain() {
    for (auto view : swapchain_image_views_) {
        vkDestroyImageView(device_, view, nullptr);
    }
    swapchain_image_views_.clear();

    if (swapchain_ != VK_NULL_HANDLE) {
        vkDestroySwapchainKHR(device_, swapchain_, nullptr);
        swapchain_ = VK_NULL_HANDLE;
    }
}

// ============================================================================
// Descriptor Management
// ============================================================================

VkDescriptorPool GraphicsDevice::create_descriptor_pool(uint32_t max_sets,
    const std::vector<VkDescriptorPoolSize>& pool_sizes) {
    VkDescriptorPoolCreateInfo pool_info{};
    pool_info.sType = VK_STRUCTURE_TYPE_DESCRIPTOR_POOL_CREATE_INFO;
    pool_info.poolSizeCount = static_cast<uint32_t>(pool_sizes.size());
    pool_info.pPoolSizes = pool_sizes.data();
    pool_info.maxSets = max_sets;

    VkDescriptorPool pool;
    VkResult result = vkCreateDescriptorPool(device_, &pool_info, nullptr, &pool);
    if (result != VK_SUCCESS) {
        throw std::runtime_error("Failed to create descriptor pool");
    }
    return pool;
}

VkDescriptorSet GraphicsDevice::allocate_descriptor_set(VkDescriptorPool pool,
                                                        VkDescriptorSetLayout layout) {
    VkDescriptorSetAllocateInfo alloc_info{};
    alloc_info.sType = VK_STRUCTURE_TYPE_DESCRIPTOR_SET_ALLOCATE_INFO;
    alloc_info.descriptorPool = pool;
    alloc_info.descriptorSetCount = 1;
    alloc_info.pSetLayouts = &layout;

    VkDescriptorSet set;
    VkResult result = vkAllocateDescriptorSets(device_, &alloc_info, &set);
    if (result != VK_SUCCESS) {
        throw std::runtime_error("Failed to allocate descriptor set");
    }
    return set;
}

void GraphicsDevice::update_descriptor_set(VkDescriptorSet set, uint32_t binding,
                                          VkDescriptorType type, const GPUBuffer& buffer) {
    VkDescriptorBufferInfo buffer_info{};
    buffer_info.buffer = buffer.buffer;
    buffer_info.offset = 0;
    buffer_info.range = buffer.size;

    VkWriteDescriptorSet write{};
    write.sType = VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET;
    write.dstSet = set;
    write.dstBinding = binding;
    write.dstArrayElement = 0;
    write.descriptorType = type;
    write.descriptorCount = 1;
    write.pBufferInfo = &buffer_info;

    vkUpdateDescriptorSets(device_, 1, &write, 0, nullptr);
}

void GraphicsDevice::update_descriptor_set(VkDescriptorSet set, uint32_t binding,
                                          const GPUImage& image, VkSampler sampler) {
    VkDescriptorImageInfo image_info{};
    image_info.imageLayout = VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL;
    image_info.imageView = image.view;
    image_info.sampler = sampler;

    VkWriteDescriptorSet write{};
    write.sType = VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET;
    write.dstSet = set;
    write.dstBinding = binding;
    write.dstArrayElement = 0;
    write.descriptorType = VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER;
    write.descriptorCount = 1;
    write.pImageInfo = &image_info;

    vkUpdateDescriptorSets(device_, 1, &write, 0, nullptr);
}

VkSampler GraphicsDevice::create_sampler(VkFilter filter, VkSamplerAddressMode address_mode,
                                         float max_anisotropy) {
    VkSamplerCreateInfo sampler_info{};
    sampler_info.sType = VK_STRUCTURE_TYPE_SAMPLER_CREATE_INFO;
    sampler_info.magFilter = filter;
    sampler_info.minFilter = filter;
    sampler_info.addressModeU = address_mode;
    sampler_info.addressModeV = address_mode;
    sampler_info.addressModeW = address_mode;
    sampler_info.anisotropyEnable = max_anisotropy > 1.0f ? VK_TRUE : VK_FALSE;
    sampler_info.maxAnisotropy = max_anisotropy;
    sampler_info.borderColor = VK_BORDER_COLOR_INT_OPAQUE_BLACK;
    sampler_info.unnormalizedCoordinates = VK_FALSE;
    sampler_info.compareEnable = VK_FALSE;
    sampler_info.mipmapMode = VK_SAMPLER_MIPMAP_MODE_LINEAR;

    VkSampler sampler;
    VkResult result = vkCreateSampler(device_, &sampler_info, nullptr, &sampler);
    if (result != VK_SUCCESS) {
        throw std::runtime_error("Failed to create sampler");
    }
    return sampler;
}

// ============================================================================
// ShaderCompiler Implementation (GLSL → SPIR-V)
// ============================================================================

std::vector<uint32_t> ShaderCompiler::compile_glsl(
    const std::string& source,
    VkShaderStageFlagBits stage,
    const std::string& entry_point)
{
    std::cout << "Compiling " << (stage == VK_SHADER_STAGE_VERTEX_BIT ? "VERTEX" :
                                   (stage == VK_SHADER_STAGE_FRAGMENT_BIT ? "FRAGMENT" : "COMPUTE"))
              << " shader..." << std::endl;

    shaderc::Compiler compiler;
    shaderc::CompileOptions options;

    options.SetOptimizationLevel(shaderc_optimization_level_performance);
    options.SetTargetEnvironment(shaderc_target_env_vulkan, shaderc_env_version_vulkan_1_2);

    // Map Vulkan stage to shaderc stage
    shaderc_shader_kind kind;
    switch (stage) {
        case VK_SHADER_STAGE_VERTEX_BIT:
            kind = shaderc_vertex_shader;
            break;
        case VK_SHADER_STAGE_FRAGMENT_BIT:
            kind = shaderc_fragment_shader;
            break;
        case VK_SHADER_STAGE_COMPUTE_BIT:
            kind = shaderc_compute_shader;
            break;
        default:
            last_error_ = "Unsupported shader stage";
            std::cout << "ERROR: " << last_error_ << std::endl;
            return {};
    }

    shaderc::SpvCompilationResult result = compiler.CompileGlslToSpv(
        source, kind, "shader.glsl", entry_point.c_str(), options);

    if (result.GetCompilationStatus() != shaderc_compilation_status_success) {
        last_error_ = result.GetErrorMessage();
        std::cout << "SHADER COMPILATION FAILED:" << std::endl;
        std::cout << last_error_ << std::endl;
        return {};
    }

    std::vector<uint32_t> spirv = {result.cbegin(), result.cend()};
    std::cout << "SUCCESS: Compiled to " << spirv.size() << " SPIR-V words" << std::endl;

    return spirv;
}

// ============================================================================
// VirtualTextureCache Implementation
// ============================================================================

VirtualTextureCache::VirtualTextureCache(GraphicsDevice* device, uint32_t cache_size_mb)
    : device_(device)
{
    // Each tile is 128 KB (as per spec)
    const uint32_t tile_size_kb = 128;
    max_tiles_ = (cache_size_mb * 1024) / tile_size_kb;
}

VirtualTextureCache::~VirtualTextureCache() {
    clear();
}

const VirtualTextureTile* VirtualTextureCache::request_tile(uint32_t x, uint32_t y, uint32_t mip) {
    uint64_t key = tile_key(x, y, mip);

    auto it = tiles_.find(key);
    if (it != tiles_.end()) {
        // Tile is cached, update access time
        it->second.last_access_frame = current_frame_;
        return &it->second;
    }

    // Need to load tile
    if (tiles_.size() >= max_tiles_) {
        evict_lru();
    }

    VirtualTextureTile tile;
    tile.x = x;
    tile.y = y;
    tile.mip_level = mip;
    tile.last_access_frame = current_frame_;
    load_tile(tile);

    tiles_[key] = tile;
    return &tiles_[key];
}

void VirtualTextureCache::clear() {
    for (auto& [key, tile] : tiles_) {
        if (tile.gpu_image.is_valid()) {
            device_->destroy_image(tile.gpu_image);
        }
    }
    tiles_.clear();
}

void VirtualTextureCache::evict_lru() {
    if (tiles_.empty()) return;

    // Find least recently used tile
    uint64_t oldest_key = 0;
    uint64_t oldest_frame = UINT64_MAX;

    for (const auto& [key, tile] : tiles_) {
        if (tile.last_access_frame < oldest_frame) {
            oldest_frame = tile.last_access_frame;
            oldest_key = key;
        }
    }

    // Evict it
    auto it = tiles_.find(oldest_key);
    if (it != tiles_.end()) {
        if (it->second.gpu_image.is_valid()) {
            device_->destroy_image(it->second.gpu_image);
        }
        tiles_.erase(it);
    }
}

void VirtualTextureCache::load_tile(VirtualTextureTile& tile) {
    // For now, create a placeholder texture
    // In a real implementation, this would load actual tile data from disk/procedural gen
    const uint32_t tile_size = 256; // 256x256 RGBA8 = 256 KB

    tile.gpu_image = device_->create_image(
        tile_size, tile_size,
        VK_FORMAT_R8G8B8A8_UNORM,
        VK_IMAGE_USAGE_SAMPLED_BIT | VK_IMAGE_USAGE_TRANSFER_DST_BIT,
        1
    );

    tile.resident = true;
}

// ============================================================================
// RenderContext Implementation
// ============================================================================

RenderContext::RenderContext(GraphicsDevice* device)
    : device_(device)
{
}

RenderContext::~RenderContext() {
    if (device_->device() == VK_NULL_HANDLE) return;

    vkDeviceWaitIdle(device_->device());

    cleanup_framebuffers();
    
    // Destroy descriptor resources
    if (descriptor_pool_ != VK_NULL_HANDLE) {
        vkDestroyDescriptorPool(device_->device(), descriptor_pool_, nullptr);
    }
    if (frame_descriptor_layout_ != VK_NULL_HANDLE) {
        vkDestroyDescriptorSetLayout(device_->device(), frame_descriptor_layout_, nullptr);
    }
    
    // Destroy uniform buffers
    for (auto& buffer : frame_uniform_buffers_) {
        device_->destroy_buffer(buffer);
    }

    if (depth_prepass_ != VK_NULL_HANDLE) {
        vkDestroyRenderPass(device_->device(), depth_prepass_, nullptr);
    }
    if (forward_pass_ != VK_NULL_HANDLE) {
        vkDestroyRenderPass(device_->device(), forward_pass_, nullptr);
    }
    if (post_pass_ != VK_NULL_HANDLE) {
        vkDestroyRenderPass(device_->device(), post_pass_, nullptr);
    }

    // Destroy sync objects
    for (size_t i = 0; i < MAX_FRAMES_IN_FLIGHT; i++) {
        if (i < image_available_semaphores_.size() && image_available_semaphores_[i] != VK_NULL_HANDLE) {
            vkDestroySemaphore(device_->device(), image_available_semaphores_[i], nullptr);
        }
        if (i < render_finished_semaphores_.size() && render_finished_semaphores_[i] != VK_NULL_HANDLE) {
            vkDestroySemaphore(device_->device(), render_finished_semaphores_[i], nullptr);
        }
        if (i < in_flight_fences_.size() && in_flight_fences_[i] != VK_NULL_HANDLE) {
            vkDestroyFence(device_->device(), in_flight_fences_[i], nullptr);
        }
    }
}

bool RenderContext::initialize(uint32_t width, uint32_t height) {
    width_ = width;
    height_ = height;

    if (!create_render_passes()) return false;
    if (!create_framebuffers()) return false;
    if (!create_sync_objects()) return false;
    if (!create_command_buffers()) return false;
    if (!create_uniform_buffers()) return false;
    if (!create_descriptor_resources()) return false;

    // Set default camera to view typical terrain
    // Assumes terrain is centered around (32, 0, 32) for 64x64 terrain
    camera_.position = {32.0f, 100.0f, 80.0f};
    camera_.target = {32.0f, 0.0f, 32.0f};
    camera_.up = {0.0f, 1.0f, 0.0f};
    camera_.fov = 60.0f;
    camera_.near_plane = 0.1f;
    camera_.far_plane = 1000.0f;

    std::cout << "Default camera set: pos(" << camera_.position[0] << ", "
              << camera_.position[1] << ", " << camera_.position[2] << ") -> target("
              << camera_.target[0] << ", " << camera_.target[1] << ", "
              << camera_.target[2] << ")" << std::endl;

    return true;
}

uint32_t RenderContext::begin_frame() {
    // Wait for this frame's fence
    vkWaitForFences(device_->device(), 1, &in_flight_fences_[current_frame_], VK_TRUE, UINT64_MAX);

    // Acquire next swapchain image if we have a swapchain
    if (device_->has_swapchain()) {
        VkResult result = vkAcquireNextImageKHR(device_->device(), device_->swapchain(),
            UINT64_MAX, image_available_semaphores_[current_frame_], VK_NULL_HANDLE,
            &current_image_index_);

        if (result == VK_ERROR_OUT_OF_DATE_KHR) {
            // Swapchain needs recreation
            return UINT32_MAX;
        } else if (result != VK_SUCCESS && result != VK_SUBOPTIMAL_KHR) {
            std::cerr << "Failed to acquire swapchain image: " << result << std::endl;
            return UINT32_MAX;
        }
    } else {
        current_image_index_ = 0;
    }

    vkResetFences(device_->device(), 1, &in_flight_fences_[current_frame_]);
    vkResetCommandBuffer(command_buffers_[current_frame_], 0);

    // Begin command buffer
    VkCommandBufferBeginInfo begin_info{};
    begin_info.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO;
    vkBeginCommandBuffer(command_buffers_[current_frame_], &begin_info);

    stats_ = {};
    draw_queue_.clear();
    frame_started_ = true;
    frame_number_++;

    return current_image_index_;
}

void RenderContext::draw_mesh(const GPUMesh& mesh, const Pipeline& material_pipeline,
                             const std::array<float, 16>& transform) {
    if (!mesh.is_valid() || !material_pipeline.is_valid()) {
        std::cout << "draw_mesh: SKIPPED - mesh valid=" << mesh.is_valid() 
                  << ", pipeline valid=" << material_pipeline.is_valid() << std::endl;
        return;
    }

    DrawCommand cmd;
    cmd.mesh = &mesh;
    cmd.pipeline = &material_pipeline;
    cmd.transform = transform;
    cmd.color = {1.0f, 1.0f, 1.0f, 1.0f};  // Default white
    draw_queue_.push_back(cmd);

    // Debug: Log draw command on first few frames
    if (frame_number_ <= 3) {
        std::cout << "draw_mesh: queued mesh with " << mesh.vertex_count 
                  << " vertices, " << mesh.index_count << " indices" << std::endl;
    }

    stats_.draw_calls++;
    stats_.triangles += mesh.index_count / 3;
    stats_.vertices += mesh.vertex_count;
}

void RenderContext::draw_terrain(const GPUMesh& terrain_mesh, const Pipeline& pipeline) {
    std::array<float, 16> identity = {
        1, 0, 0, 0,
        0, 1, 0, 0,
        0, 0, 1, 0,
        0, 0, 0, 1
    };
    draw_mesh(terrain_mesh, pipeline, identity);
}

void RenderContext::flush_draws() {
    record_draw_commands();
}

void RenderContext::end_frame() {
    if (!frame_started_) return;

    // Flush any remaining draw commands
    flush_draws();

    vkEndCommandBuffer(command_buffers_[current_frame_]);

    // Submit command buffer
    VkSubmitInfo submit_info{};
    submit_info.sType = VK_STRUCTURE_TYPE_SUBMIT_INFO;

    VkSemaphore wait_semaphores[] = {image_available_semaphores_[current_frame_]};
    VkPipelineStageFlags wait_stages[] = {VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT};
    
    if (device_->has_swapchain()) {
        submit_info.waitSemaphoreCount = 1;
        submit_info.pWaitSemaphores = wait_semaphores;
        submit_info.pWaitDstStageMask = wait_stages;
    }

    submit_info.commandBufferCount = 1;
    submit_info.pCommandBuffers = &command_buffers_[current_frame_];

    VkSemaphore signal_semaphores[] = {render_finished_semaphores_[current_frame_]};
    if (device_->has_swapchain()) {
        submit_info.signalSemaphoreCount = 1;
        submit_info.pSignalSemaphores = signal_semaphores;
    }

    VkResult result = vkQueueSubmit(device_->graphics_queue(), 1, &submit_info, 
                                    in_flight_fences_[current_frame_]);
    if (result != VK_SUCCESS) {
        std::cerr << "Failed to submit draw command buffer: " << result << std::endl;
    }

    // Present if we have a swapchain
    if (device_->has_swapchain()) {
        VkPresentInfoKHR present_info{};
        present_info.sType = VK_STRUCTURE_TYPE_PRESENT_INFO_KHR;
        present_info.waitSemaphoreCount = 1;
        present_info.pWaitSemaphores = signal_semaphores;

        VkSwapchainKHR swapchains[] = {device_->swapchain()};
        present_info.swapchainCount = 1;
        present_info.pSwapchains = swapchains;
        present_info.pImageIndices = &current_image_index_;

        result = vkQueuePresentKHR(device_->present_queue(), &present_info);
        if (result == VK_ERROR_OUT_OF_DATE_KHR || result == VK_SUBOPTIMAL_KHR) {
            // Swapchain needs recreation - caller should handle this
        } else if (result != VK_SUCCESS) {
            std::cerr << "Failed to present: " << result << std::endl;
        }
    }

    current_frame_ = (current_frame_ + 1) % MAX_FRAMES_IN_FLIGHT;
    frame_started_ = false;
}

void RenderContext::resize(uint32_t width, uint32_t height) {
    vkDeviceWaitIdle(device_->device());
    
    width_ = width;
    height_ = height;
    
    cleanup_framebuffers();
    create_framebuffers();
}

bool RenderContext::create_render_passes() {
    // =========================================================================
    // Depth Pre-pass
    // =========================================================================
    {
        VkAttachmentDescription depth_attachment{};
        depth_attachment.format = VK_FORMAT_D32_SFLOAT;
        depth_attachment.samples = VK_SAMPLE_COUNT_1_BIT;
        depth_attachment.loadOp = VK_ATTACHMENT_LOAD_OP_CLEAR;
        depth_attachment.storeOp = VK_ATTACHMENT_STORE_OP_STORE;
        depth_attachment.stencilLoadOp = VK_ATTACHMENT_LOAD_OP_DONT_CARE;
        depth_attachment.stencilStoreOp = VK_ATTACHMENT_STORE_OP_DONT_CARE;
        depth_attachment.initialLayout = VK_IMAGE_LAYOUT_UNDEFINED;
        depth_attachment.finalLayout = VK_IMAGE_LAYOUT_DEPTH_STENCIL_READ_ONLY_OPTIMAL;

        VkAttachmentReference depth_ref{};
        depth_ref.attachment = 0;
        depth_ref.layout = VK_IMAGE_LAYOUT_DEPTH_STENCIL_ATTACHMENT_OPTIMAL;

        VkSubpassDescription subpass{};
        subpass.pipelineBindPoint = VK_PIPELINE_BIND_POINT_GRAPHICS;
        subpass.colorAttachmentCount = 0;
        subpass.pDepthStencilAttachment = &depth_ref;

        VkSubpassDependency dependency{};
        dependency.srcSubpass = VK_SUBPASS_EXTERNAL;
        dependency.dstSubpass = 0;
        dependency.srcStageMask = VK_PIPELINE_STAGE_EARLY_FRAGMENT_TESTS_BIT;
        dependency.srcAccessMask = 0;
        dependency.dstStageMask = VK_PIPELINE_STAGE_EARLY_FRAGMENT_TESTS_BIT;
        dependency.dstAccessMask = VK_ACCESS_DEPTH_STENCIL_ATTACHMENT_WRITE_BIT;

        VkRenderPassCreateInfo render_pass_info{};
        render_pass_info.sType = VK_STRUCTURE_TYPE_RENDER_PASS_CREATE_INFO;
        render_pass_info.attachmentCount = 1;
        render_pass_info.pAttachments = &depth_attachment;
        render_pass_info.subpassCount = 1;
        render_pass_info.pSubpasses = &subpass;
        render_pass_info.dependencyCount = 1;
        render_pass_info.pDependencies = &dependency;

        VkResult result = vkCreateRenderPass(device_->device(), &render_pass_info,
                                            nullptr, &depth_prepass_);
        if (result != VK_SUCCESS) {
            std::cerr << "Failed to create depth prepass: " << result << std::endl;
            return false;
        }
    }

    // =========================================================================
    // Forward Pass (main rendering)
    // =========================================================================
    {
        // Color attachment
        VkAttachmentDescription color_attachment{};
        color_attachment.format = device_->has_swapchain() ? 
            device_->swapchain_format() : VK_FORMAT_R8G8B8A8_UNORM;
        color_attachment.samples = VK_SAMPLE_COUNT_1_BIT;
        color_attachment.loadOp = VK_ATTACHMENT_LOAD_OP_CLEAR;
        color_attachment.storeOp = VK_ATTACHMENT_STORE_OP_STORE;
        color_attachment.stencilLoadOp = VK_ATTACHMENT_LOAD_OP_DONT_CARE;
        color_attachment.stencilStoreOp = VK_ATTACHMENT_STORE_OP_DONT_CARE;
        color_attachment.initialLayout = VK_IMAGE_LAYOUT_UNDEFINED;
        color_attachment.finalLayout = device_->has_swapchain() ?
            VK_IMAGE_LAYOUT_PRESENT_SRC_KHR : VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL;

        // Depth attachment (reuse from depth prepass)
        VkAttachmentDescription depth_attachment{};
        depth_attachment.format = VK_FORMAT_D32_SFLOAT;
        depth_attachment.samples = VK_SAMPLE_COUNT_1_BIT;
        // FIX: Clear depth since we aren't running the depth pre-pass yet
        depth_attachment.loadOp = VK_ATTACHMENT_LOAD_OP_CLEAR;
        depth_attachment.storeOp = VK_ATTACHMENT_STORE_OP_DONT_CARE;
        depth_attachment.stencilLoadOp = VK_ATTACHMENT_LOAD_OP_DONT_CARE;
        depth_attachment.stencilStoreOp = VK_ATTACHMENT_STORE_OP_DONT_CARE;
        // FIX: Start from undefined layout since we clear it
        depth_attachment.initialLayout = VK_IMAGE_LAYOUT_UNDEFINED;
        depth_attachment.finalLayout = VK_IMAGE_LAYOUT_DEPTH_STENCIL_ATTACHMENT_OPTIMAL;

        VkAttachmentReference color_ref{};
        color_ref.attachment = 0;
        color_ref.layout = VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL;

        VkAttachmentReference depth_ref{};
        depth_ref.attachment = 1;
        depth_ref.layout = VK_IMAGE_LAYOUT_DEPTH_STENCIL_ATTACHMENT_OPTIMAL;

        VkSubpassDescription subpass{};
        subpass.pipelineBindPoint = VK_PIPELINE_BIND_POINT_GRAPHICS;
        subpass.colorAttachmentCount = 1;
        subpass.pColorAttachments = &color_ref;
        subpass.pDepthStencilAttachment = &depth_ref;

        std::array<VkSubpassDependency, 2> dependencies{};
        dependencies[0].srcSubpass = VK_SUBPASS_EXTERNAL;
        dependencies[0].dstSubpass = 0;
        dependencies[0].srcStageMask = VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT |
                                       VK_PIPELINE_STAGE_EARLY_FRAGMENT_TESTS_BIT;
        dependencies[0].srcAccessMask = 0;
        dependencies[0].dstStageMask = VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT |
                                       VK_PIPELINE_STAGE_EARLY_FRAGMENT_TESTS_BIT;
        dependencies[0].dstAccessMask = VK_ACCESS_COLOR_ATTACHMENT_WRITE_BIT |
                                        VK_ACCESS_DEPTH_STENCIL_ATTACHMENT_WRITE_BIT;

        dependencies[1].srcSubpass = 0;
        dependencies[1].dstSubpass = VK_SUBPASS_EXTERNAL;
        dependencies[1].srcStageMask = VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT;
        dependencies[1].srcAccessMask = VK_ACCESS_COLOR_ATTACHMENT_WRITE_BIT;
        dependencies[1].dstStageMask = VK_PIPELINE_STAGE_BOTTOM_OF_PIPE_BIT;
        dependencies[1].dstAccessMask = 0;

        std::array<VkAttachmentDescription, 2> attachments = {color_attachment, depth_attachment};

        VkRenderPassCreateInfo render_pass_info{};
        render_pass_info.sType = VK_STRUCTURE_TYPE_RENDER_PASS_CREATE_INFO;
        render_pass_info.attachmentCount = static_cast<uint32_t>(attachments.size());
        render_pass_info.pAttachments = attachments.data();
        render_pass_info.subpassCount = 1;
        render_pass_info.pSubpasses = &subpass;
        render_pass_info.dependencyCount = static_cast<uint32_t>(dependencies.size());
        render_pass_info.pDependencies = dependencies.data();

        VkResult result = vkCreateRenderPass(device_->device(), &render_pass_info,
                                            nullptr, &forward_pass_);
        if (result != VK_SUCCESS) {
            std::cerr << "Failed to create forward pass: " << result << std::endl;
            return false;
        }
    }

    return true;
}

bool RenderContext::create_framebuffers() {
    // Create depth image
    depth_image_ = device_->create_image(
        width_, height_,
        VK_FORMAT_D32_SFLOAT,
        VK_IMAGE_USAGE_DEPTH_STENCIL_ATTACHMENT_BIT,
        1
    );

    if (device_->has_swapchain()) {
        // Create framebuffers for each swapchain image
        const auto& views = device_->swapchain_image_views();
        swapchain_framebuffers_.resize(views.size());

        for (size_t i = 0; i < views.size(); i++) {
            std::array<VkImageView, 2> attachments = {
                views[i],
                depth_image_.view
            };

            VkFramebufferCreateInfo fb_info{};
            fb_info.sType = VK_STRUCTURE_TYPE_FRAMEBUFFER_CREATE_INFO;
            fb_info.renderPass = forward_pass_;
            fb_info.attachmentCount = static_cast<uint32_t>(attachments.size());
            fb_info.pAttachments = attachments.data();
            fb_info.width = width_;
            fb_info.height = height_;
            fb_info.layers = 1;

            VkResult result = vkCreateFramebuffer(device_->device(), &fb_info, nullptr,
                                                 &swapchain_framebuffers_[i]);
            if (result != VK_SUCCESS) {
                std::cerr << "Failed to create framebuffer: " << result << std::endl;
                return false;
            }
        }
    } else {
        // Create offscreen color image for headless rendering
        color_image_ = device_->create_image(
            width_, height_,
            VK_FORMAT_R8G8B8A8_UNORM,
            VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT | VK_IMAGE_USAGE_TRANSFER_SRC_BIT,
            1
        );

        swapchain_framebuffers_.resize(1);
        
        std::array<VkImageView, 2> attachments = {
            color_image_.view,
            depth_image_.view
        };

        VkFramebufferCreateInfo fb_info{};
        fb_info.sType = VK_STRUCTURE_TYPE_FRAMEBUFFER_CREATE_INFO;
        fb_info.renderPass = forward_pass_;
        fb_info.attachmentCount = static_cast<uint32_t>(attachments.size());
        fb_info.pAttachments = attachments.data();
        fb_info.width = width_;
        fb_info.height = height_;
        fb_info.layers = 1;

        VkResult result = vkCreateFramebuffer(device_->device(), &fb_info, nullptr,
                                             &swapchain_framebuffers_[0]);
        if (result != VK_SUCCESS) {
            std::cerr << "Failed to create offscreen framebuffer: " << result << std::endl;
            return false;
        }
    }

    // Create depth-only framebuffer for depth prepass
    VkFramebufferCreateInfo depth_fb_info{};
    depth_fb_info.sType = VK_STRUCTURE_TYPE_FRAMEBUFFER_CREATE_INFO;
    depth_fb_info.renderPass = depth_prepass_;
    depth_fb_info.attachmentCount = 1;
    depth_fb_info.pAttachments = &depth_image_.view;
    depth_fb_info.width = width_;
    depth_fb_info.height = height_;
    depth_fb_info.layers = 1;

    VkResult result = vkCreateFramebuffer(device_->device(), &depth_fb_info, nullptr,
                                         &depth_framebuffer_);
    if (result != VK_SUCCESS) {
        std::cerr << "Failed to create depth framebuffer: " << result << std::endl;
        return false;
    }

    return true;
}

bool RenderContext::create_sync_objects() {
    image_available_semaphores_.resize(MAX_FRAMES_IN_FLIGHT);
    render_finished_semaphores_.resize(MAX_FRAMES_IN_FLIGHT);
    in_flight_fences_.resize(MAX_FRAMES_IN_FLIGHT);

    VkSemaphoreCreateInfo semaphore_info{};
    semaphore_info.sType = VK_STRUCTURE_TYPE_SEMAPHORE_CREATE_INFO;

    VkFenceCreateInfo fence_info{};
    fence_info.sType = VK_STRUCTURE_TYPE_FENCE_CREATE_INFO;
    fence_info.flags = VK_FENCE_CREATE_SIGNALED_BIT;

    for (size_t i = 0; i < MAX_FRAMES_IN_FLIGHT; i++) {
        if (vkCreateSemaphore(device_->device(), &semaphore_info, nullptr, 
                             &image_available_semaphores_[i]) != VK_SUCCESS ||
            vkCreateSemaphore(device_->device(), &semaphore_info, nullptr,
                             &render_finished_semaphores_[i]) != VK_SUCCESS ||
            vkCreateFence(device_->device(), &fence_info, nullptr,
                         &in_flight_fences_[i]) != VK_SUCCESS) {
            std::cerr << "Failed to create synchronization objects" << std::endl;
            return false;
        }
    }

    return true;
}

bool RenderContext::create_command_buffers() {
    command_buffers_.resize(MAX_FRAMES_IN_FLIGHT);

    VkCommandBufferAllocateInfo alloc_info{};
    alloc_info.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO;
    alloc_info.commandPool = device_->command_pool();
    alloc_info.level = VK_COMMAND_BUFFER_LEVEL_PRIMARY;
    alloc_info.commandBufferCount = static_cast<uint32_t>(MAX_FRAMES_IN_FLIGHT);

    VkResult result = vkAllocateCommandBuffers(device_->device(), &alloc_info, 
                                               command_buffers_.data());
    if (result != VK_SUCCESS) {
        std::cerr << "Failed to allocate command buffers: " << result << std::endl;
        return false;
    }

    return true;
}

bool RenderContext::create_uniform_buffers() {
    VkDeviceSize buffer_size = sizeof(FrameUniforms);
    frame_uniform_buffers_.resize(MAX_FRAMES_IN_FLIGHT);

    for (size_t i = 0; i < MAX_FRAMES_IN_FLIGHT; i++) {
        frame_uniform_buffers_[i] = device_->create_buffer(
            buffer_size,
            VK_BUFFER_USAGE_UNIFORM_BUFFER_BIT,
            VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT
        );
    }

    return true;
}

bool RenderContext::create_descriptor_resources() {
    // Create descriptor set layout for frame uniforms
    VkDescriptorSetLayoutBinding ubo_binding{};
    ubo_binding.binding = 0;
    ubo_binding.descriptorType = VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER;
    ubo_binding.descriptorCount = 1;
    ubo_binding.stageFlags = VK_SHADER_STAGE_VERTEX_BIT | VK_SHADER_STAGE_FRAGMENT_BIT;

    VkDescriptorSetLayoutCreateInfo layout_info{};
    layout_info.sType = VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO;
    layout_info.bindingCount = 1;
    layout_info.pBindings = &ubo_binding;

    VkResult result = vkCreateDescriptorSetLayout(device_->device(), &layout_info, nullptr,
                                                  &frame_descriptor_layout_);
    if (result != VK_SUCCESS) {
        std::cerr << "Failed to create frame descriptor layout: " << result << std::endl;
        return false;
    }

    // Create descriptor pool
    VkDescriptorPoolSize pool_size{};
    pool_size.type = VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER;
    pool_size.descriptorCount = static_cast<uint32_t>(MAX_FRAMES_IN_FLIGHT);

    VkDescriptorPoolCreateInfo pool_info{};
    pool_info.sType = VK_STRUCTURE_TYPE_DESCRIPTOR_POOL_CREATE_INFO;
    pool_info.poolSizeCount = 1;
    pool_info.pPoolSizes = &pool_size;
    pool_info.maxSets = static_cast<uint32_t>(MAX_FRAMES_IN_FLIGHT);

    result = vkCreateDescriptorPool(device_->device(), &pool_info, nullptr, &descriptor_pool_);
    if (result != VK_SUCCESS) {
        std::cerr << "Failed to create descriptor pool: " << result << std::endl;
        return false;
    }

    // Allocate descriptor sets
    std::vector<VkDescriptorSetLayout> layouts(MAX_FRAMES_IN_FLIGHT, frame_descriptor_layout_);

    VkDescriptorSetAllocateInfo alloc_info{};
    alloc_info.sType = VK_STRUCTURE_TYPE_DESCRIPTOR_SET_ALLOCATE_INFO;
    alloc_info.descriptorPool = descriptor_pool_;
    alloc_info.descriptorSetCount = static_cast<uint32_t>(MAX_FRAMES_IN_FLIGHT);
    alloc_info.pSetLayouts = layouts.data();

    frame_descriptor_sets_.resize(MAX_FRAMES_IN_FLIGHT);
    result = vkAllocateDescriptorSets(device_->device(), &alloc_info, frame_descriptor_sets_.data());
    if (result != VK_SUCCESS) {
        std::cerr << "Failed to allocate descriptor sets: " << result << std::endl;
        return false;
    }

    // Update descriptor sets with uniform buffers
    for (size_t i = 0; i < MAX_FRAMES_IN_FLIGHT; i++) {
        VkDescriptorBufferInfo buffer_info{};
        buffer_info.buffer = frame_uniform_buffers_[i].buffer;
        buffer_info.offset = 0;
        buffer_info.range = sizeof(FrameUniforms);

        VkWriteDescriptorSet write{};
        write.sType = VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET;
        write.dstSet = frame_descriptor_sets_[i];
        write.dstBinding = 0;
        write.dstArrayElement = 0;
        write.descriptorType = VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER;
        write.descriptorCount = 1;
        write.pBufferInfo = &buffer_info;

        vkUpdateDescriptorSets(device_->device(), 1, &write, 0, nullptr);
    }

    return true;
}

void RenderContext::cleanup_framebuffers() {
    for (auto fb : swapchain_framebuffers_) {
        if (fb != VK_NULL_HANDLE) {
            vkDestroyFramebuffer(device_->device(), fb, nullptr);
        }
    }
    swapchain_framebuffers_.clear();

    if (depth_framebuffer_ != VK_NULL_HANDLE) {
        vkDestroyFramebuffer(device_->device(), depth_framebuffer_, nullptr);
        depth_framebuffer_ = VK_NULL_HANDLE;
    }

    if (depth_image_.is_valid()) {
        device_->destroy_image(depth_image_);
    }
    if (color_image_.is_valid()) {
        device_->destroy_image(color_image_);
    }
}

void RenderContext::update_camera_uniforms() {
    FrameUniforms uniforms{};
    
    // Compute view and projection matrices
    compute_view_matrix(uniforms.view, camera_);
    float aspect = static_cast<float>(width_) / static_cast<float>(height_);
    compute_projection_matrix(uniforms.projection, camera_.fov, aspect, 
                             camera_.near_plane, camera_.far_plane);
    multiply_matrices(uniforms.view_projection, uniforms.projection, uniforms.view);
    
    // Camera position
    uniforms.camera_pos[0] = camera_.position[0];
    uniforms.camera_pos[1] = camera_.position[1];
    uniforms.camera_pos[2] = camera_.position[2];
    uniforms.camera_pos[3] = 1.0f;
    
    // Time
    uniforms.time[0] = static_cast<float>(frame_number_) / 60.0f;  // Total time
    uniforms.time[1] = 1.0f / 60.0f;  // Delta time
    uniforms.time[2] = static_cast<float>(frame_number_);  // Frame
    uniforms.time[3] = 0.0f;

    // Fog parameters — dead zone of ~1.5 chunks (96 units), then gentle ramp
    uniforms.fog_params[0] = 96.0f;    // fog_start: distance before fog begins
    uniforms.fog_params[1] = 0.0018f;  // fog_density: exponential coefficient
    uniforms.fog_params[2] = 0.65f;    // fog_max: maximum fog opacity
    uniforms.fog_params[3] = 0.0f;

    // Fog color (consistent across clear color and shader)
    uniforms.fog_color[0] = 0.35f;
    uniforms.fog_color[1] = 0.45f;
    uniforms.fog_color[2] = 0.65f;
    uniforms.fog_color[3] = 1.0f;

    // Update the current frame's uniform buffer
    device_->update_buffer(frame_uniform_buffers_[current_frame_], &uniforms, sizeof(uniforms));
}

void RenderContext::record_draw_commands() {
    // DEBUG: Log draw state (only on first few frames to avoid spam)
    if (frame_number_ <= 5) {
        std::cout << "=== RENDER DEBUG (frame " << frame_number_ << ") ===" << std::endl;
        std::cout << "Draw queue size: " << draw_queue_.size() << std::endl;
        std::cout << "Camera position: (" << camera_.position[0] << ", "
                  << camera_.position[1] << ", " << camera_.position[2] << ")" << std::endl;
        std::cout << "Camera target: (" << camera_.target[0] << ", "
                  << camera_.target[1] << ", " << camera_.target[2] << ")" << std::endl;
        std::cout << "Viewport: " << width_ << "x" << height_ << std::endl;

        if (!draw_queue_.empty()) {
            const auto& first = draw_queue_[0];
            std::cout << "First mesh - vertices: " << first.mesh->vertex_count
                      << ", indices: " << first.mesh->index_count << std::endl;
        }
        std::cout << "===================" << std::endl;
    }

    // Check if we have anything to render (meshes or ImGui UI)
    ImDrawData* pending_imgui = ImGui::GetDrawData();
    bool has_imgui = pending_imgui && pending_imgui->CmdListsCount > 0;

    if (draw_queue_.empty() && !has_imgui) {
        if (frame_number_ <= 5) {
            std::cout << "WARNING: Draw queue is EMPTY and no ImGui data!" << std::endl;
        }
        return;
    }

    VkCommandBuffer cmd = command_buffers_[current_frame_];

    // Update uniforms
    update_camera_uniforms();

    // Begin forward render pass
    VkRenderPassBeginInfo render_pass_info{};
    render_pass_info.sType = VK_STRUCTURE_TYPE_RENDER_PASS_BEGIN_INFO;
    render_pass_info.renderPass = forward_pass_;
    render_pass_info.framebuffer = swapchain_framebuffers_[current_image_index_];
    render_pass_info.renderArea.offset = {0, 0};
    render_pass_info.renderArea.extent = {width_, height_};

    std::array<VkClearValue, 2> clear_values{};
    clear_values[0].color = {{0.35f, 0.45f, 0.65f, 1.0f}};  // Match fog color for seamless horizon
    clear_values[1].depthStencil = {1.0f, 0};

    render_pass_info.clearValueCount = static_cast<uint32_t>(clear_values.size());
    render_pass_info.pClearValues = clear_values.data();

    vkCmdBeginRenderPass(cmd, &render_pass_info, VK_SUBPASS_CONTENTS_INLINE);

    // Set viewport and scissor
    VkViewport viewport{};
    viewport.x = 0.0f;
    viewport.y = 0.0f;
    viewport.width = static_cast<float>(width_);
    viewport.height = static_cast<float>(height_);
    viewport.minDepth = 0.0f;
    viewport.maxDepth = 1.0f;
    vkCmdSetViewport(cmd, 0, 1, &viewport);

    VkRect2D scissor{};
    scissor.offset = {0, 0};
    scissor.extent = {width_, height_};
    vkCmdSetScissor(cmd, 0, 1, &scissor);

    // Draw all queued meshes
    const Pipeline* current_pipeline = nullptr;
    
    for (const auto& draw : draw_queue_) {
        // Bind pipeline if changed
        if (draw.pipeline != current_pipeline) {
            current_pipeline = draw.pipeline;
            vkCmdBindPipeline(cmd, VK_PIPELINE_BIND_POINT_GRAPHICS, current_pipeline->pipeline);
            
            // Bind descriptor set for frame uniforms
            vkCmdBindDescriptorSets(cmd, VK_PIPELINE_BIND_POINT_GRAPHICS, 
                                   current_pipeline->layout, 0, 1,
                                   &frame_descriptor_sets_[current_frame_], 0, nullptr);
        }

        // Push constants for per-draw transform
        PushConstants push{};
        std::memcpy(push.model, draw.transform.data(), sizeof(push.model));
        std::memcpy(push.color, draw.color.data(), sizeof(push.color));
        vkCmdPushConstants(cmd, current_pipeline->layout, 
                          VK_SHADER_STAGE_VERTEX_BIT | VK_SHADER_STAGE_FRAGMENT_BIT,
                          0, sizeof(push), &push);

        // Bind vertex and index buffers
        VkBuffer vertex_buffers[] = {draw.mesh->vertex_buffer.buffer};
        VkDeviceSize offsets[] = {0};
        vkCmdBindVertexBuffers(cmd, 0, 1, vertex_buffers, offsets);
        vkCmdBindIndexBuffer(cmd, draw.mesh->index_buffer.buffer, 0, VK_INDEX_TYPE_UINT32);

        // Debug: Log draw call details on first few frames
        if (frame_number_ <= 3) {
            std::cout << "  vkCmdDrawIndexed: " << draw.mesh->index_count << " indices, "
                      << draw.mesh->vertex_count << " vertices" << std::endl;
            std::cout << "  push.color: (" << push.color[0] << ", " << push.color[1] << ", " 
                      << push.color[2] << ", " << push.color[3] << ")" << std::endl;
        }

        // Draw!
        vkCmdDrawIndexed(cmd, draw.mesh->index_count, 1, 0, 0, 0);
    }

    // Render Dear ImGui draw data on top of the scene (if available)
    // Only render if ImGui::Render() was called this frame (GetDrawData != null)
    // and the draw data is valid (non-zero command lists)
    ImDrawData* imgui_draw_data = ImGui::GetDrawData();
    if (imgui_draw_data && imgui_draw_data->Valid && imgui_draw_data->CmdListsCount > 0) {
        ImGui_ImplVulkan_RenderDrawData(imgui_draw_data, cmd);
    }

    vkCmdEndRenderPass(cmd);
}

// Matrix utilities
void RenderContext::compute_view_matrix(float* out, const Camera& cam) {
    // Compute look-at matrix
    float fx = cam.target[0] - cam.position[0];
    float fy = cam.target[1] - cam.position[1];
    float fz = cam.target[2] - cam.position[2];
    float len = std::sqrt(fx*fx + fy*fy + fz*fz);
    fx /= len; fy /= len; fz /= len;
    
    float sx = fy * cam.up[2] - fz * cam.up[1];
    float sy = fz * cam.up[0] - fx * cam.up[2];
    float sz = fx * cam.up[1] - fy * cam.up[0];
    len = std::sqrt(sx*sx + sy*sy + sz*sz);
    sx /= len; sy /= len; sz /= len;
    
    float ux = sy * fz - sz * fy;
    float uy = sz * fx - sx * fz;
    float uz = sx * fy - sy * fx;
    
    // Column-major layout
    out[0] = sx;  out[4] = sy;  out[8]  = sz;  out[12] = -(sx*cam.position[0] + sy*cam.position[1] + sz*cam.position[2]);
    out[1] = ux;  out[5] = uy;  out[9]  = uz;  out[13] = -(ux*cam.position[0] + uy*cam.position[1] + uz*cam.position[2]);
    out[2] = -fx; out[6] = -fy; out[10] = -fz; out[14] = fx*cam.position[0] + fy*cam.position[1] + fz*cam.position[2];
    out[3] = 0;   out[7] = 0;   out[11] = 0;   out[15] = 1;
}

void RenderContext::compute_projection_matrix(float* out, float fov, float aspect, float near, float far) {
    // Vulkan clip space: X [-1,1], Y [-1,1], Z [0,1]
    // Y is flipped (negative) for Vulkan's coordinate system
    float fov_rad = fov * 3.14159265358979f / 180.0f;
    float tan_half_fov = std::tan(fov_rad / 2.0f);
    
    std::memset(out, 0, 16 * sizeof(float));
    out[0] = 1.0f / (aspect * tan_half_fov);
    out[5] = -1.0f / tan_half_fov;  // Flip Y for Vulkan
    // FIX: Standard Vulkan depth [0,1] mapping requires P[2][2] to be negative for standard RH view
    // P[2][2] = f / (n - f) = -f / (f - n)
    out[10] = -far / (far - near);
    out[11] = -1.0f;
    out[14] = -(near * far) / (far - near);  // FIXED: was positive, needs negative
}

void RenderContext::multiply_matrices(float* out, const float* a, const float* b) {
    float temp[16];
    for (int i = 0; i < 4; i++) {
        for (int j = 0; j < 4; j++) {
            temp[i + j*4] = 0;
            for (int k = 0; k < 4; k++) {
                temp[i + j*4] += a[i + k*4] * b[k + j*4];
            }
        }
    }
    std::memcpy(out, temp, sizeof(temp));
}

// ============================================================================
// GraphicsSystem Implementation
// ============================================================================

GraphicsSystem::GraphicsSystem() = default;

GraphicsSystem::~GraphicsSystem() {
    shutdown();
}

bool GraphicsSystem::initialize(uint32_t width, uint32_t height, bool enable_validation, bool enable_vsync) {
    return initialize_with_surface(VK_NULL_HANDLE, width, height, enable_validation, enable_vsync);
}

bool GraphicsSystem::initialize_with_surface(VkSurfaceKHR surface, uint32_t width, 
                                             uint32_t height, bool enable_validation, bool enable_vsync) {
    device_ = std::make_unique<GraphicsDevice>();
    if (!device_->initialize(surface, enable_validation, enable_vsync)) {
        return false;
    }

    // Create swapchain if we have a surface
    if (surface != VK_NULL_HANDLE) {
        if (!device_->create_swapchain(width, height)) {
            return false;
        }
    }

    render_context_ = std::make_unique<RenderContext>(device_.get());
    if (!render_context_->initialize(width, height)) {
        return false;
    }

    shader_compiler_ = std::make_unique<ShaderCompiler>();
    texture_cache_ = std::make_unique<VirtualTextureCache>(device_.get());

    return true;
}

bool GraphicsSystem::create_instance_with_extensions(const std::vector<std::string>& extensions,
                                                     bool enable_validation) {
    device_ = std::make_unique<GraphicsDevice>();
    if (!device_->create_instance_with_extensions(extensions, enable_validation)) {
        device_.reset();
        return false;
    }
    return true;
}

bool GraphicsSystem::complete_initialization_with_surface(uint64_t surface, uint32_t width,
                                                          uint32_t height, bool enable_vsync) {
    if (!device_) {
        std::cerr << "Cannot complete init: device not created (call create_instance_with_extensions first)" << std::endl;
        return false;
    }
    
    VkSurfaceKHR vk_surface = reinterpret_cast<VkSurfaceKHR>(surface);
    
    if (!device_->complete_initialization(vk_surface, enable_vsync)) {
        return false;
    }
    
    // Create swapchain if we have a surface
    if (vk_surface != VK_NULL_HANDLE) {
        if (!device_->create_swapchain(width, height)) {
            return false;
        }
    }
    
    render_context_ = std::make_unique<RenderContext>(device_.get());
    if (!render_context_->initialize(width, height)) {
        return false;
    }
    
    shader_compiler_ = std::make_unique<ShaderCompiler>();
    texture_cache_ = std::make_unique<VirtualTextureCache>(device_.get());
    
    std::cout << "GraphicsSystem initialization complete with surface" << std::endl;
    return true;
}

uint64_t GraphicsSystem::get_instance_handle() const {
    if (device_) {
        return device_->get_instance_handle();
    }
    return 0;
}

void GraphicsSystem::shutdown() {
    if (device_ && device_->is_initialized()) {
        vkDeviceWaitIdle(device_->device());
    }

    shutdown_imgui();

    if (default_pipeline_created_ && default_pipeline_.is_valid()) {
        device_->destroy_pipeline(default_pipeline_);
        default_pipeline_created_ = false;
    }

    texture_cache_.reset();
    shader_compiler_.reset();
    render_context_.reset();
    device_.reset();
}

void GraphicsSystem::resize(uint32_t width, uint32_t height) {
    if (!device_ || !device_->is_initialized()) return;
    
    vkDeviceWaitIdle(device_->device());
    
    if (device_->has_swapchain()) {
        device_->recreate_swapchain(width, height);
    }
    
    if (render_context_) {
        render_context_->resize(width, height);
    }
}

GPUMesh GraphicsSystem::upload_mesh(const props::Mesh& mesh) {
    return device_->upload_mesh(mesh);
}

void GraphicsSystem::destroy_mesh(GPUMesh& mesh) {
    device_->destroy_mesh(mesh);
}

Pipeline GraphicsSystem::create_material_pipeline(const std::string& vertex_glsl,
                                                  const std::string& fragment_glsl) {
    // Compile shaders
    auto vertex_spirv = shader_compiler_->compile_glsl(
        vertex_glsl, VK_SHADER_STAGE_VERTEX_BIT);
    auto fragment_spirv = shader_compiler_->compile_glsl(
        fragment_glsl, VK_SHADER_STAGE_FRAGMENT_BIT);

    if (vertex_spirv.empty() || fragment_spirv.empty()) {
        std::cerr << "Shader compilation failed: " << shader_compiler_->get_error() << std::endl;
        return {};
    }

    // Create pipeline with render pass
    PipelineConfig config;
    config.cull_mode = VK_CULL_MODE_NONE;  // DEBUG: Disable culling for visibility
    return device_->create_pipeline(config, render_context_->render_pass(),
                                   vertex_spirv, fragment_spirv);
}

void GraphicsSystem::destroy_pipeline(Pipeline& pipeline) {
    device_->destroy_pipeline(pipeline);
}

Pipeline GraphicsSystem::create_default_pipeline() {
    if (default_pipeline_created_) {
        std::cout << "Returning cached default pipeline" << std::endl;
        return default_pipeline_;
    }

    std::cout << "Creating default pipeline..." << std::endl;

    std::string vertex_src = get_default_vertex_shader();
    std::string fragment_src = get_default_fragment_shader();

    std::cout << "Vertex shader length: " << vertex_src.length() << std::endl;
    std::cout << "Fragment shader length: " << fragment_src.length() << std::endl;

    default_pipeline_ = create_material_pipeline(vertex_src, fragment_src);

    if (default_pipeline_.is_valid()) {
        std::cout << "SUCCESS: Default pipeline created" << std::endl;
        default_pipeline_created_ = true;
    } else {
        std::cout << "FAILURE: Default pipeline creation failed!" << std::endl;
        std::cout << "Check shader compilation errors above" << std::endl;
    }

    return default_pipeline_;
}

void GraphicsSystem::begin_frame() {
    render_context_->begin_frame();
    texture_cache_->advance_frame();
}

void GraphicsSystem::draw_mesh(const GPUMesh& mesh, const Pipeline& pipeline,
                              const std::array<float, 16>& transform) {
    render_context_->draw_mesh(mesh, pipeline, transform);
}

void GraphicsSystem::draw_mesh(const GPUMesh& mesh, const Pipeline& pipeline,
                              const std::array<float, 16>& transform,
                              const std::array<float, 4>& color) {
    // For now, just call the basic version - color is handled via push constants
    render_context_->draw_mesh(mesh, pipeline, transform);
}

void GraphicsSystem::end_frame() {
    render_context_->end_frame();
}

void GraphicsSystem::set_camera(const Camera& camera) {
    render_context_->set_camera(camera);
}

void GraphicsSystem::add_light(const Light& light) {
    render_context_->add_light(light);
}

void GraphicsSystem::clear_lights() {
    render_context_->clear_lights();
}

const RenderStats& GraphicsSystem::get_stats() const {
    return render_context_->stats();
}

std::string GraphicsSystem::get_default_vertex_shader() const {
    return R"(
#version 450

layout(location = 0) in vec3 inPosition;
layout(location = 1) in vec3 inNormal;
layout(location = 2) in vec2 inUV;
layout(location = 3) in vec4 inColor;

layout(location = 0) out vec3 fragNormal;
layout(location = 1) out vec3 fragWorldPos;
layout(location = 2) out vec2 fragUV;
layout(location = 3) out vec4 fragColor;

layout(binding = 0) uniform FrameUniforms {
    mat4 view;
    mat4 projection;
    mat4 viewProjection;
    vec4 cameraPos;
    vec4 time;
    vec4 fogParams;
    vec4 fogColor;
} frame;

layout(push_constant) uniform PushConstants {
    mat4 model;
    vec4 color;
} push;

void main() {
    vec4 worldPos = push.model * vec4(inPosition, 1.0);
    gl_Position = frame.viewProjection * worldPos;
    
    fragWorldPos = worldPos.xyz;
    fragNormal = mat3(push.model) * inNormal;
    fragUV = inUV;
    // Combine vertex color with push constant color (allows tinting)
    fragColor = inColor * push.color;
}
)";
}

std::string GraphicsSystem::get_default_fragment_shader() const {
    return R"(
#version 450

layout(location = 0) in vec3 fragNormal;
layout(location = 1) in vec3 fragWorldPos;
layout(location = 2) in vec2 fragUV;
layout(location = 3) in vec4 fragColor;

layout(location = 0) out vec4 outColor;

layout(binding = 0) uniform FrameUniforms {
    mat4 view;
    mat4 projection;
    mat4 viewProjection;
    vec4 cameraPos;
    vec4 time;
    vec4 fogParams;   // x=fog_start, y=fog_density, z=fog_max, w=unused
    vec4 fogColor;    // RGB fog color
} frame;

layout(push_constant) uniform PushConstants {
    mat4 model;
    vec4 color;
} push;

void main() {
    vec3 normal = normalize(fragNormal);

    // Sun light from upper-right
    vec3 sunDir = normalize(vec3(0.5, 0.8, 0.3));
    vec3 sunColor = vec3(1.0, 0.95, 0.85);

    // Sky light from above (ambient fill)
    vec3 skyDir = vec3(0.0, 1.0, 0.0);
    vec3 skyColor = vec3(0.4, 0.5, 0.7);

    // Ground bounce from below
    vec3 groundColor = vec3(0.2, 0.15, 0.1);

    // Diffuse lighting
    float sunDiffuse = max(dot(normal, sunDir), 0.0);
    float skyDiffuse = max(dot(normal, skyDir), 0.0);
    float groundDiffuse = max(dot(normal, -skyDir), 0.0) * 0.3;

    // Combine lighting
    vec3 lighting = sunColor * sunDiffuse
                  + skyColor * skyDiffuse * 0.15
                  + groundColor * groundDiffuse;

    // Add ambient minimum
    lighting += vec3(0.05);

    // Apply vertex color (biome/material color)
    vec3 albedo = fragColor.rgb;
    float luminance = dot(albedo, vec3(0.2126, 0.7152, 0.0722));
    albedo = clamp(mix(vec3(luminance), albedo, 1.3), 0.0, 1.0);
    vec3 finalColor = albedo * lighting;

    // Distance fog with dead zone around the camera
    float dist = length(fragWorldPos - frame.cameraPos.xyz);
    float fogDist = max(dist - frame.fogParams.x, 0.0);
    float fogFactor = 1.0 - exp(-fogDist * frame.fogParams.y);
    fogFactor = clamp(fogFactor, 0.0, frame.fogParams.z);
    finalColor = mix(finalColor, frame.fogColor.rgb, fogFactor);

    // Gamma correction
    finalColor = pow(finalColor, vec3(1.0 / 2.2));

    outColor = vec4(finalColor, fragColor.a);
}
)";
}

// =============================================================================
// Dear ImGui integration implementation
// =============================================================================

static void imgui_check_vk_result(VkResult result) {
    if (result != VK_SUCCESS) {
        std::cerr << "[ImGui] Vulkan error: " << result << std::endl;
    }
}

bool GraphicsSystem::init_imgui(uint64_t sdl_window_handle) {
    if (imgui_initialized_) return true;
    if (!device_ || !device_->is_initialized() || !render_context_) {
        std::cerr << "Cannot init ImGui: graphics system not initialized" << std::endl;
        return false;
    }

    // Create ImGui context
    IMGUI_CHECKVERSION();
    ImGui::CreateContext();
    ImGuiIO& io = ImGui::GetIO();
    io.ConfigFlags |= ImGuiConfigFlags_NavEnableKeyboard;
    ImGui::StyleColorsDark();

    // Create a dedicated descriptor pool for ImGui
    // FIX: Increased pool size from 100 to 1000 to prevent overflow during long runs
    VkDescriptorPoolSize pool_sizes[] = {
        { VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER, 1000 },
    };
    VkDescriptorPoolCreateInfo pool_info{};
    pool_info.sType = VK_STRUCTURE_TYPE_DESCRIPTOR_POOL_CREATE_INFO;
    pool_info.flags = VK_DESCRIPTOR_POOL_CREATE_FREE_DESCRIPTOR_SET_BIT;
    pool_info.maxSets = 1000;  // FIX: Match pool size
    pool_info.poolSizeCount = 1;
    pool_info.pPoolSizes = pool_sizes;
    VkResult res = vkCreateDescriptorPool(device_->device(), &pool_info, nullptr, &imgui_descriptor_pool_);
    if (res != VK_SUCCESS) {
        std::cerr << "Failed to create ImGui descriptor pool: " << res << std::endl;
        return false;
    }

#if HAS_SDL2
    // Initialize the SDL2 backend (pass the SDL_Window pointer)
    SDL_Window* window = reinterpret_cast<SDL_Window*>(sdl_window_handle);
    if (window) {
        ImGui_ImplSDL2_InitForVulkan(window);
    }
#else
    (void)sdl_window_handle;  // unused without SDL2
#endif

    // Initialize the Vulkan backend
    ImGui_ImplVulkan_InitInfo init_info{};
    init_info.Instance = device_->instance();
    init_info.PhysicalDevice = device_->physical_device();
    init_info.Device = device_->device();
    init_info.QueueFamily = device_->queue_families().graphics_family.value_or(0);
    init_info.Queue = device_->graphics_queue();
    init_info.DescriptorPool = imgui_descriptor_pool_;
    init_info.MinImageCount = 2;
    init_info.ImageCount = static_cast<uint32_t>(device_->swapchain_image_views().size());
    if (init_info.ImageCount < 2) init_info.ImageCount = 2;
    init_info.MSAASamples = VK_SAMPLE_COUNT_1_BIT;
    init_info.RenderPass = render_context_->render_pass();
    init_info.CheckVkResultFn = imgui_check_vk_result;

    ImGui_ImplVulkan_Init(&init_info);

    // Upload font textures to the GPU.
    // ImGui 1.91+ simplified this to not require a command buffer parameter.
    ImGui_ImplVulkan_CreateFontsTexture();

    imgui_initialized_ = true;
#if HAS_SDL2
    std::cout << "Dear ImGui initialized (Vulkan + SDL2)" << std::endl;
#else
    std::cout << "Dear ImGui initialized (Vulkan only, no SDL2)" << std::endl;
#endif
    return true;
}

void GraphicsSystem::shutdown_imgui() {
    if (!imgui_initialized_) return;

    if (device_ && device_->is_initialized()) {
        vkDeviceWaitIdle(device_->device());
    }

    ImGui_ImplVulkan_Shutdown();
#if HAS_SDL2
    ImGui_ImplSDL2_Shutdown();
#endif
    ImGui::DestroyContext();

    if (imgui_descriptor_pool_ != VK_NULL_HANDLE && device_ && device_->is_initialized()) {
        vkDestroyDescriptorPool(device_->device(), imgui_descriptor_pool_, nullptr);
        imgui_descriptor_pool_ = VK_NULL_HANDLE;
    }

    imgui_initialized_ = false;
    std::cout << "Dear ImGui shut down" << std::endl;
}

void GraphicsSystem::imgui_new_frame() {
    if (!imgui_initialized_) return;
    // Prevent double-NewFrame without an intervening Render
    if (imgui_frame_active_) {
        // Discard the previous unfinished frame
        ImGui::EndFrame();
    }
    ImGui_ImplVulkan_NewFrame();
#if HAS_SDL2
    ImGui_ImplSDL2_NewFrame();
#endif
    ImGui::NewFrame();
    imgui_frame_active_ = true;
}

void GraphicsSystem::imgui_render() {
    if (!imgui_initialized_ || !imgui_frame_active_) return;
    ImGui::Render();
    imgui_frame_active_ = false;
    // The actual draw data is consumed in RenderContext::record_draw_commands()
    // via ImGui_ImplVulkan_RenderDrawData(ImGui::GetDrawData(), cmd).
}

} // namespace graphics
