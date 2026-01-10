cmake_minimum_required(VERSION 3.14)
project(procengine_cpp LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Build options
option(NO_GRAPHICS "Build without Vulkan graphics support (headless/CI)" OFF)
option(BUILD_TESTS "Build C++ unit tests" OFF)
option(ENABLE_PROFILING "Enable timing instrumentation" OFF)
option(BUILD_LAUNCHER "Build standalone executable launcher" OFF)
option(BUILD_STATIC_LIB "Build static library for embedding" OFF)

# Find dependencies
# Try python3 first, fall back to python (Windows uses 'python')
execute_process(
    COMMAND python3 -m pybind11 --cmakedir
    OUTPUT_VARIABLE pybind11_DIR
    OUTPUT_STRIP_TRAILING_WHITESPACE
    RESULT_VARIABLE PYBIND11_RESULT
)
if(NOT PYBIND11_RESULT EQUAL 0)
    execute_process(
        COMMAND python -m pybind11 --cmakedir
        OUTPUT_VARIABLE pybind11_DIR
        OUTPUT_STRIP_TRAILING_WHITESPACE
    )
endif()
list(APPEND CMAKE_PREFIX_PATH ${pybind11_DIR})
find_package(pybind11 CONFIG REQUIRED)
find_package(OpenSSL REQUIRED)

# Vulkan and shaderc are only required if NOT building headless
if(NOT NO_GRAPHICS)
    find_package(Vulkan REQUIRED)
else()
    message(STATUS "Building in headless mode (NO_GRAPHICS=ON)")
endif()

# Find shaderc - platform-specific search (only if graphics enabled)
if(NOT NO_GRAPHICS)
    if(WIN32)
        # Windows: shaderc is part of Vulkan SDK
        # Use both CMake variable and environment variable
        set(SHADERC_SEARCH_PATHS "")
        set(SHADERC_INCLUDE_PATHS "")

        if(DEFINED VULKAN_SDK)
            list(APPEND SHADERC_SEARCH_PATHS "${VULKAN_SDK}/Lib" "${VULKAN_SDK}/lib")
            list(APPEND SHADERC_INCLUDE_PATHS "${VULKAN_SDK}/Include" "${VULKAN_SDK}/include")
        endif()
        if(DEFINED ENV{VULKAN_SDK})
            list(APPEND SHADERC_SEARCH_PATHS "$ENV{VULKAN_SDK}/Lib" "$ENV{VULKAN_SDK}/lib")
            list(APPEND SHADERC_INCLUDE_PATHS "$ENV{VULKAN_SDK}/Include" "$ENV{VULKAN_SDK}/include")
        endif()
        # Also check relative to Vulkan found location
        if(Vulkan_INCLUDE_DIR)
            get_filename_component(VULKAN_SDK_FROM_INCLUDE "${Vulkan_INCLUDE_DIR}" DIRECTORY)
            list(APPEND SHADERC_SEARCH_PATHS "${VULKAN_SDK_FROM_INCLUDE}/Lib" "${VULKAN_SDK_FROM_INCLUDE}/lib")
            list(APPEND SHADERC_INCLUDE_PATHS "${Vulkan_INCLUDE_DIR}")
        endif()

        message(STATUS "Searching for shaderc in: ${SHADERC_SEARCH_PATHS}")

        find_library(SHADERC_LIB
            NAMES shaderc_combined shaderc_shared shaderc
            PATHS ${SHADERC_SEARCH_PATHS}
            NO_DEFAULT_PATH
        )
        find_path(SHADERC_INCLUDE_DIR
            NAMES shaderc/shaderc.hpp
            PATHS ${SHADERC_INCLUDE_PATHS}
            NO_DEFAULT_PATH
        )
    elseif(APPLE)
        # =======================================================================
        # macOS: Check for direct override first, then Vulkan SDK, then Homebrew
        # =======================================================================
        
        # Allow direct override from CI via -DSHADERC_LIB=... -DSHADERC_INCLUDE_DIR=...
        if(SHADERC_LIB AND EXISTS "${SHADERC_LIB}")
            message(STATUS "Using provided SHADERC_LIB: ${SHADERC_LIB}")
            # SHADERC_LIB is already set, skip detection
        else()
            # Clear any invalid cached value
            unset(SHADERC_LIB CACHE)
            
            set(SHADERC_SEARCH_PATHS "")
            set(SHADERC_INCLUDE_PATHS "")

            # Priority 1: Vulkan SDK (used in CI)
            if(DEFINED VULKAN_SDK)
                message(STATUS "Checking Vulkan SDK for shaderc: ${VULKAN_SDK}")
                list(APPEND SHADERC_SEARCH_PATHS "${VULKAN_SDK}/lib")
                list(APPEND SHADERC_INCLUDE_PATHS "${VULKAN_SDK}/include")
            endif()
            if(DEFINED ENV{VULKAN_SDK})
                message(STATUS "Checking VULKAN_SDK env for shaderc: $ENV{VULKAN_SDK}")
                list(APPEND SHADERC_SEARCH_PATHS "$ENV{VULKAN_SDK}/lib")
                list(APPEND SHADERC_INCLUDE_PATHS "$ENV{VULKAN_SDK}/include")
            endif()

            # Priority 2: Homebrew shaderc (local development)
            execute_process(
                COMMAND brew --prefix shaderc
                OUTPUT_VARIABLE SHADERC_PREFIX
                OUTPUT_STRIP_TRAILING_WHITESPACE
                RESULT_VARIABLE SHADERC_BREW_RESULT
                ERROR_QUIET
            )
            if(SHADERC_BREW_RESULT EQUAL 0 AND SHADERC_PREFIX)
                message(STATUS "Found Homebrew shaderc at: ${SHADERC_PREFIX}")
                list(APPEND SHADERC_SEARCH_PATHS "${SHADERC_PREFIX}/lib")
                list(APPEND SHADERC_INCLUDE_PATHS "${SHADERC_PREFIX}/include")
            endif()

            # Priority 3: Standard Homebrew locations (fallback)
            list(APPEND SHADERC_SEARCH_PATHS "/opt/homebrew/lib" "/usr/local/lib")
            list(APPEND SHADERC_INCLUDE_PATHS "/opt/homebrew/include" "/usr/local/include")

            message(STATUS "macOS shaderc search paths: ${SHADERC_SEARCH_PATHS}")

            # Find the library - try shaderc_combined first (static), then shared
            find_library(SHADERC_LIB
                NAMES shaderc_combined libshaderc_combined.a shaderc_shared shaderc
                PATHS ${SHADERC_SEARCH_PATHS}
                NO_DEFAULT_PATH
            )
            find_path(SHADERC_INCLUDE_DIR
                NAMES shaderc/shaderc.hpp
                PATHS ${SHADERC_INCLUDE_PATHS}
                NO_DEFAULT_PATH
            )

            # If not found with NO_DEFAULT_PATH, try again with default paths
            if(NOT SHADERC_LIB)
                find_library(SHADERC_LIB
                    NAMES shaderc_combined libshaderc_combined.a shaderc_shared shaderc
                    PATHS ${SHADERC_SEARCH_PATHS}
                )
            endif()
            if(NOT SHADERC_INCLUDE_DIR)
                find_path(SHADERC_INCLUDE_DIR
                    NAMES shaderc/shaderc.hpp
                    PATHS ${SHADERC_INCLUDE_PATHS}
                )
            endif()
        endif()  # End of "if not provided directly"
    else()
        # Linux: use standard find_library (original working approach)
        find_library(SHADERC_LIB shaderc PATHS /usr/lib/x86_64-linux-gnu /usr/lib /usr/local/lib)
    endif()

    if(NOT SHADERC_LIB)
        message(FATAL_ERROR "shaderc library not found. Searched in: ${SHADERC_SEARCH_PATHS}\n"
            "On macOS:\n"
            "  - Install Vulkan SDK: https://vulkan.lunarg.com/sdk/home\n"
            "  - Or: brew install shaderc\n"
            "  - Or pass: -DVULKAN_SDK=/path/to/vulkansdk")
    endif()

    message(STATUS "Found shaderc: ${SHADERC_LIB}")
endif()

# Build module - conditionally include graphics.cpp
set(MODULE_SOURCES
    engine.cpp
    seed_registry.cpp
    terrain.cpp
    physics.cpp
    props.cpp
    materials.cpp
)

if(NOT NO_GRAPHICS)
    list(APPEND MODULE_SOURCES graphics.cpp)
endif()

pybind11_add_module(procengine_cpp ${MODULE_SOURCES})

# Add NO_GRAPHICS compile definition if building headless
if(NO_GRAPHICS)
    target_compile_definitions(procengine_cpp PRIVATE NO_GRAPHICS)
endif()

# Add include directories for shaderc if found (Windows/macOS)
if(NOT NO_GRAPHICS AND SHADERC_INCLUDE_DIR)
    message(STATUS "Found shaderc includes: ${SHADERC_INCLUDE_DIR}")
    target_include_directories(procengine_cpp PRIVATE ${SHADERC_INCLUDE_DIR})
endif()

# Link libraries - conditionally include Vulkan and shaderc
target_link_libraries(procengine_cpp PRIVATE OpenSSL::Crypto)

if(NOT NO_GRAPHICS)
    target_link_libraries(procengine_cpp PRIVATE
        Vulkan::Vulkan
        ${SHADERC_LIB}
    )
endif()

# =============================================================================
# Static library target (for embedding in launcher)
# =============================================================================

if(BUILD_STATIC_LIB OR BUILD_LAUNCHER)
    message(STATUS "Building static library for embedding")

    add_library(procengine_static STATIC ${MODULE_SOURCES})

    target_compile_definitions(procengine_static PRIVATE
        PROCENGINE_STATIC_BUILD
    )

    if(NO_GRAPHICS)
        target_compile_definitions(procengine_static PRIVATE NO_GRAPHICS)
    endif()

    if(SHADERC_INCLUDE_DIR)
        target_include_directories(procengine_static PRIVATE ${SHADERC_INCLUDE_DIR})
    endif()

    target_link_libraries(procengine_static PRIVATE OpenSSL::Crypto)

    if(NOT NO_GRAPHICS)
        target_link_libraries(procengine_static PRIVATE
            Vulkan::Vulkan
            ${SHADERC_LIB}
        )
    endif()

    # Need pybind11 headers
    target_include_directories(procengine_static PRIVATE ${pybind11_INCLUDE_DIRS})
    target_link_libraries(procengine_static PRIVATE pybind11::headers)
endif()

# =============================================================================
# Standalone launcher executable
# =============================================================================

if(BUILD_LAUNCHER)
    message(STATUS "Building standalone launcher executable")

    find_package(Python3 REQUIRED COMPONENTS Development)

    add_executable(ProceduralEngine launcher.cpp)

    target_include_directories(ProceduralEngine PRIVATE
        ${Python3_INCLUDE_DIRS}
        ${pybind11_INCLUDE_DIRS}
    )

    target_link_libraries(ProceduralEngine PRIVATE
        procengine_static
        Python3::Python
        OpenSSL::Crypto
    )

    if(NOT NO_GRAPHICS)
        target_link_libraries(ProceduralEngine PRIVATE
            Vulkan::Vulkan
            ${SHADERC_LIB}
        )
    endif()

    if(NO_GRAPHICS)
        target_compile_definitions(ProceduralEngine PRIVATE NO_GRAPHICS)
    endif()

    # Set output name
    set_target_properties(ProceduralEngine PROPERTIES
        OUTPUT_NAME "ProceduralEngine"
        RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin"
    )

    # Windows-specific: embed manifest, set subsystem
    if(WIN32)
        set_target_properties(ProceduralEngine PROPERTIES
            WIN32_EXECUTABLE FALSE  # FALSE = console app, TRUE = GUI app
        )
    endif()

    # Install rules
    install(TARGETS ProceduralEngine
        RUNTIME DESTINATION bin
    )
endif()