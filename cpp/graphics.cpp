#include "graphics.h"
#include <shaderc/shaderc.hpp>
#include <cstring>
#include <cmath>
#include <algorithm>
#include <stdexcept>
#include <set>
#include <iostream>

namespace graphics {

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

bool GraphicsDevice::initialize(VkSurfaceKHR surface, bool enable_validation) {
    surface_ = surface;

    if (!create_instance(enable_validation)) return false;
    if (enable_validation && !setup_debug_messenger()) return false;
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

    auto extensions = get_required_extensions(enable_validation);
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
    GPUMesh gpu_mesh;
    gpu_mesh.vertex_count = static_cast<uint32_t>(mesh.vertices.size());
    gpu_mesh.index_count = static_cast<uint32_t>(mesh.indices.size());

    // Interleave vertex data (position + normal)
    struct Vertex {
        float px, py, pz;
        float nx, ny, nz;
    };

    std::vector<Vertex> vertices(mesh.vertices.size());
    for (size_t i = 0; i < mesh.vertices.size(); ++i) {
        vertices[i].px = mesh.vertices[i].x;
        vertices[i].py = mesh.vertices[i].y;
        vertices[i].pz = mesh.vertices[i].z;
        vertices[i].nx = mesh.normals[i].x;
        vertices[i].ny = mesh.normals[i].y;
        vertices[i].nz = mesh.normals[i].z;
    }

    VkDeviceSize vertex_buffer_size = sizeof(Vertex) * vertices.size();
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

Pipeline GraphicsDevice::create_pipeline(const PipelineConfig& config, VkRenderPass render_pass) {
    Pipeline pipeline;

    // For now, create a simple descriptor layout (we'll expand this later)
    VkDescriptorSetLayoutCreateInfo layout_info{};
    layout_info.sType = VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO;
    layout_info.bindingCount = 0;
    layout_info.pBindings = nullptr;

    VkResult result = vkCreateDescriptorSetLayout(device_, &layout_info, nullptr, &pipeline.descriptor_layout);
    if (result != VK_SUCCESS) {
        std::cerr << "Failed to create descriptor set layout: " << result << std::endl;
        return pipeline;  // Return invalid pipeline
    }

    // Create pipeline layout
    VkPipelineLayoutCreateInfo pipeline_layout_info{};
    pipeline_layout_info.sType = VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO;
    pipeline_layout_info.setLayoutCount = 1;
    pipeline_layout_info.pSetLayouts = &pipeline.descriptor_layout;

    result = vkCreatePipelineLayout(device_, &pipeline_layout_info, nullptr, &pipeline.layout);
    if (result != VK_SUCCESS) {
        std::cerr << "Failed to create pipeline layout: " << result << std::endl;
        vkDestroyDescriptorSetLayout(device_, pipeline.descriptor_layout, nullptr);
        pipeline.descriptor_layout = VK_NULL_HANDLE;
        return pipeline;  // Return invalid pipeline
    }

    // Note: Actual pipeline creation requires shader modules, which we'll create
    // in the ShaderCompiler. For now, return partially initialized pipeline.
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
}

// ============================================================================
// ShaderCompiler Implementation (GLSL → SPIR-V)
// ============================================================================

std::vector<uint32_t> ShaderCompiler::compile_glsl(
    const std::string& source,
    VkShaderStageFlagBits stage,
    const std::string& entry_point)
{
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
            return {};
    }

    shaderc::SpvCompilationResult result = compiler.CompileGlslToSpv(
        source, kind, "shader.glsl", entry_point.c_str(), options);

    if (result.GetCompilationStatus() != shaderc_compilation_status_success) {
        last_error_ = result.GetErrorMessage();
        return {};
    }

    return {result.cbegin(), result.cend()};
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

    cleanup_framebuffers();

    if (depth_prepass_ != VK_NULL_HANDLE) {
        vkDestroyRenderPass(device_->device(), depth_prepass_, nullptr);
    }
    if (forward_pass_ != VK_NULL_HANDLE) {
        vkDestroyRenderPass(device_->device(), forward_pass_, nullptr);
    }
    if (post_pass_ != VK_NULL_HANDLE) {
        vkDestroyRenderPass(device_->device(), post_pass_, nullptr);
    }

    if (image_available_semaphore_ != VK_NULL_HANDLE) {
        vkDestroySemaphore(device_->device(), image_available_semaphore_, nullptr);
    }
    if (render_finished_semaphore_ != VK_NULL_HANDLE) {
        vkDestroySemaphore(device_->device(), render_finished_semaphore_, nullptr);
    }
    if (in_flight_fence_ != VK_NULL_HANDLE) {
        vkDestroyFence(device_->device(), in_flight_fence_, nullptr);
    }
}

bool RenderContext::initialize(uint32_t width, uint32_t height) {
    width_ = width;
    height_ = height;

    if (!create_render_passes()) return false;
    if (!create_framebuffers()) return false;
    if (!create_sync_objects()) return false;

    // Allocate command buffer
    VkCommandBufferAllocateInfo alloc_info{};
    alloc_info.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO;
    alloc_info.commandPool = device_->command_pool();
    alloc_info.level = VK_COMMAND_BUFFER_LEVEL_PRIMARY;
    alloc_info.commandBufferCount = 1;

    vkAllocateCommandBuffers(device_->device(), &alloc_info, &command_buffer_);

    return true;
}

void RenderContext::begin_frame() {
    vkWaitForFences(device_->device(), 1, &in_flight_fence_, VK_TRUE, UINT64_MAX);
    vkResetFences(device_->device(), 1, &in_flight_fence_);

    vkResetCommandBuffer(command_buffer_, 0);

    VkCommandBufferBeginInfo begin_info{};
    begin_info.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO;
    vkBeginCommandBuffer(command_buffer_, &begin_info);

    stats_ = {};
    frame_number_++;
}

void RenderContext::draw_mesh(const GPUMesh& mesh, const Pipeline& material_pipeline,
                             const std::array<float, 16>& transform) {
    // Simplified draw - in real implementation would bind pipeline, descriptors, etc.
    stats_.draw_calls++;
    stats_.triangles += mesh.index_count / 3;
    stats_.vertices += mesh.vertex_count;
}

void RenderContext::draw_terrain(const GPUMesh& terrain_mesh, const Pipeline& pipeline) {
    draw_mesh(terrain_mesh, pipeline, {1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1});
}

void RenderContext::end_frame() {
    vkEndCommandBuffer(command_buffer_);

    VkSubmitInfo submit_info{};
    submit_info.sType = VK_STRUCTURE_TYPE_SUBMIT_INFO;
    submit_info.commandBufferCount = 1;
    submit_info.pCommandBuffers = &command_buffer_;

    vkQueueSubmit(device_->graphics_queue(), 1, &submit_info, in_flight_fence_);
}

void RenderContext::resize(uint32_t width, uint32_t height) {
    width_ = width;
    height_ = height;
    cleanup_framebuffers();
    create_framebuffers();
}

bool RenderContext::create_render_passes() {
    // Simplified render pass creation
    // In full implementation, would create proper depth prepass, forward+, and post passes
    VkAttachmentDescription color_attachment{};
    color_attachment.format = VK_FORMAT_R8G8B8A8_UNORM;
    color_attachment.samples = VK_SAMPLE_COUNT_1_BIT;
    color_attachment.loadOp = VK_ATTACHMENT_LOAD_OP_CLEAR;
    color_attachment.storeOp = VK_ATTACHMENT_STORE_OP_STORE;
    color_attachment.initialLayout = VK_IMAGE_LAYOUT_UNDEFINED;
    color_attachment.finalLayout = VK_IMAGE_LAYOUT_PRESENT_SRC_KHR;

    VkAttachmentReference color_ref{};
    color_ref.attachment = 0;
    color_ref.layout = VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL;

    VkSubpassDescription subpass{};
    subpass.pipelineBindPoint = VK_PIPELINE_BIND_POINT_GRAPHICS;
    subpass.colorAttachmentCount = 1;
    subpass.pColorAttachments = &color_ref;

    VkRenderPassCreateInfo render_pass_info{};
    render_pass_info.sType = VK_STRUCTURE_TYPE_RENDER_PASS_CREATE_INFO;
    render_pass_info.attachmentCount = 1;
    render_pass_info.pAttachments = &color_attachment;
    render_pass_info.subpassCount = 1;
    render_pass_info.pSubpasses = &subpass;

    VkResult result = vkCreateRenderPass(device_->device(), &render_pass_info,
                                        nullptr, &forward_pass_);
    return result == VK_SUCCESS;
}

bool RenderContext::create_framebuffers() {
    // Create render targets
    depth_image_ = device_->create_image(
        width_, height_,
        VK_FORMAT_D32_SFLOAT,
        VK_IMAGE_USAGE_DEPTH_STENCIL_ATTACHMENT_BIT,
        1
    );

    color_image_ = device_->create_image(
        width_, height_,
        VK_FORMAT_R8G8B8A8_UNORM,
        VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT | VK_IMAGE_USAGE_SAMPLED_BIT,
        1
    );

    return true;
}

bool RenderContext::create_sync_objects() {
    VkSemaphoreCreateInfo semaphore_info{};
    semaphore_info.sType = VK_STRUCTURE_TYPE_SEMAPHORE_CREATE_INFO;

    VkFenceCreateInfo fence_info{};
    fence_info.sType = VK_STRUCTURE_TYPE_FENCE_CREATE_INFO;
    fence_info.flags = VK_FENCE_CREATE_SIGNALED_BIT;

    VkResult result = vkCreateSemaphore(device_->device(), &semaphore_info, nullptr, &image_available_semaphore_);
    if (result != VK_SUCCESS) {
        std::cerr << "Failed to create image available semaphore: " << result << std::endl;
        return false;
    }

    result = vkCreateSemaphore(device_->device(), &semaphore_info, nullptr, &render_finished_semaphore_);
    if (result != VK_SUCCESS) {
        std::cerr << "Failed to create render finished semaphore: " << result << std::endl;
        vkDestroySemaphore(device_->device(), image_available_semaphore_, nullptr);
        image_available_semaphore_ = VK_NULL_HANDLE;
        return false;
    }

    result = vkCreateFence(device_->device(), &fence_info, nullptr, &in_flight_fence_);
    if (result != VK_SUCCESS) {
        std::cerr << "Failed to create in-flight fence: " << result << std::endl;
        vkDestroySemaphore(device_->device(), image_available_semaphore_, nullptr);
        vkDestroySemaphore(device_->device(), render_finished_semaphore_, nullptr);
        image_available_semaphore_ = VK_NULL_HANDLE;
        render_finished_semaphore_ = VK_NULL_HANDLE;
        return false;
    }

    return true;
}

void RenderContext::cleanup_framebuffers() {
    if (depth_image_.is_valid()) {
        device_->destroy_image(depth_image_);
    }
    if (color_image_.is_valid()) {
        device_->destroy_image(color_image_);
    }
}

// ============================================================================
// GraphicsSystem Implementation
// ============================================================================

GraphicsSystem::GraphicsSystem() = default;

GraphicsSystem::~GraphicsSystem() {
    shutdown();
}

bool GraphicsSystem::initialize(uint32_t width, uint32_t height, bool enable_validation) {
    device_ = std::make_unique<GraphicsDevice>();
    if (!device_->initialize(VK_NULL_HANDLE, enable_validation)) {
        return false;
    }

    render_context_ = std::make_unique<RenderContext>(device_.get());
    if (!render_context_->initialize(width, height)) {
        return false;
    }

    shader_compiler_ = std::make_unique<ShaderCompiler>();
    texture_cache_ = std::make_unique<VirtualTextureCache>(device_.get());

    return true;
}

void GraphicsSystem::shutdown() {
    if (device_ && device_->is_initialized()) {
        vkDeviceWaitIdle(device_->device());
    }

    texture_cache_.reset();
    shader_compiler_.reset();
    render_context_.reset();
    device_.reset();
}

GPUMesh GraphicsSystem::upload_mesh(const props::Mesh& mesh) {
    return device_->upload_mesh(mesh);
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

    // Create shader modules
    ShaderModule vertex_shader = device_->create_shader_module(
        vertex_spirv, VK_SHADER_STAGE_VERTEX_BIT);
    ShaderModule fragment_shader = device_->create_shader_module(
        fragment_spirv, VK_SHADER_STAGE_FRAGMENT_BIT);

    // Create pipeline (simplified)
    PipelineConfig config;
    Pipeline pipeline = device_->create_pipeline(config, VK_NULL_HANDLE);

    // Cleanup shader modules (pipeline has copied what it needs)
    device_->destroy_shader_module(vertex_shader);
    device_->destroy_shader_module(fragment_shader);

    return pipeline;
}

void GraphicsSystem::begin_frame() {
    render_context_->begin_frame();
    texture_cache_->advance_frame();
}

void GraphicsSystem::draw_mesh(const GPUMesh& mesh, const Pipeline& pipeline,
                              const std::array<float, 16>& transform) {
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

const RenderStats& GraphicsSystem::get_stats() const {
    return render_context_->stats();
}

} // namespace graphics
