cmake_minimum_required(VERSION 3.14)
project(procengine_cpp LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Find dependencies
execute_process(COMMAND python3 -m pybind11 --cmakedir OUTPUT_VARIABLE pybind11_DIR OUTPUT_STRIP_TRAILING_WHITESPACE)
list(APPEND CMAKE_PREFIX_PATH ${pybind11_DIR})
find_package(pybind11 CONFIG REQUIRED)
find_package(OpenSSL REQUIRED)
find_package(Vulkan REQUIRED)

# Find shaderc
find_library(SHADERC_LIB shaderc PATHS /usr/lib/x86_64-linux-gnu /usr/lib /usr/local/lib)
if(NOT SHADERC_LIB)
    message(FATAL_ERROR "shaderc library not found")
endif()

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

# Link libraries
target_link_libraries(procengine_cpp PRIVATE
    OpenSSL::Crypto
    Vulkan::Vulkan
    ${SHADERC_LIB}
)
