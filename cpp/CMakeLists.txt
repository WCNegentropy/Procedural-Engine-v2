cmake_minimum_required(VERSION 3.14)
project(procengine_cpp LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

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
find_package(Vulkan REQUIRED)

# Find shaderc - platform-specific search
if(WIN32)
    # Windows: shaderc is part of Vulkan SDK
    if(DEFINED ENV{VULKAN_SDK})
        set(SHADERC_SEARCH_PATHS
            "$ENV{VULKAN_SDK}/Lib"
            "$ENV{VULKAN_SDK}/lib"
        )
        set(SHADERC_INCLUDE_PATHS
            "$ENV{VULKAN_SDK}/Include"
            "$ENV{VULKAN_SDK}/include"
        )
    endif()
    find_library(SHADERC_LIB
        NAMES shaderc_combined shaderc_shared shaderc
        PATHS ${SHADERC_SEARCH_PATHS}
    )
    find_path(SHADERC_INCLUDE_DIR
        NAMES shaderc/shaderc.hpp
        PATHS ${SHADERC_INCLUDE_PATHS}
    )
elseif(APPLE)
    # macOS: shaderc from Homebrew
    execute_process(
        COMMAND brew --prefix shaderc
        OUTPUT_VARIABLE SHADERC_PREFIX
        OUTPUT_STRIP_TRAILING_WHITESPACE
        RESULT_VARIABLE SHADERC_BREW_RESULT
    )
    if(SHADERC_BREW_RESULT EQUAL 0)
        set(SHADERC_SEARCH_PATHS "${SHADERC_PREFIX}/lib")
        set(SHADERC_INCLUDE_PATHS "${SHADERC_PREFIX}/include")
    endif()
    find_library(SHADERC_LIB
        NAMES shaderc_combined shaderc_shared shaderc
        PATHS ${SHADERC_SEARCH_PATHS} /usr/local/lib /opt/homebrew/lib
    )
    find_path(SHADERC_INCLUDE_DIR
        NAMES shaderc/shaderc.hpp
        PATHS ${SHADERC_INCLUDE_PATHS} /usr/local/include /opt/homebrew/include
    )
else()
    # Linux: use standard find_library (original working approach)
    find_library(SHADERC_LIB shaderc PATHS /usr/lib/x86_64-linux-gnu /usr/lib /usr/local/lib)
endif()

if(NOT SHADERC_LIB)
    message(FATAL_ERROR "shaderc library not found")
endif()

message(STATUS "Found shaderc: ${SHADERC_LIB}")

# Build module
pybind11_add_module(procengine_cpp
    engine.cpp
    seed_registry.cpp
    terrain.cpp
    physics.cpp
    props.cpp
    materials.cpp
    graphics.cpp
)

# Add include directories for shaderc if found (Windows/macOS)
if(SHADERC_INCLUDE_DIR)
    message(STATUS "Found shaderc includes: ${SHADERC_INCLUDE_DIR}")
    target_include_directories(procengine_cpp PRIVATE ${SHADERC_INCLUDE_DIR})
endif()

# Link libraries
target_link_libraries(procengine_cpp PRIVATE
    OpenSSL::Crypto
    Vulkan::Vulkan
    ${SHADERC_LIB}
)
