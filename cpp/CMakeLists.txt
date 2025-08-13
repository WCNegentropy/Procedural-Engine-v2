cmake_minimum_required(VERSION 3.14)
project(procengine_cpp LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

execute_process(COMMAND python3 -m pybind11 --cmakedir OUTPUT_VARIABLE pybind11_DIR OUTPUT_STRIP_TRAILING_WHITESPACE)
list(APPEND CMAKE_PREFIX_PATH ${pybind11_DIR})
find_package(pybind11 CONFIG REQUIRED)
find_package(OpenSSL REQUIRED)

pybind11_add_module(procengine_cpp engine.cpp seed_registry.cpp)
target_link_libraries(procengine_cpp PRIVATE OpenSSL::Crypto)
