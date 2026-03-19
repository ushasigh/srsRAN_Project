#!/bin/bash
# sudo apt-get install cmake make gcc g++ pkg-config libfftw3-dev libmbedtls-dev libsctp-dev libyaml-cpp-dev libgtest-dev libzmq3-dev
# git clone https://github.com/ushasigh/srsRAN_Project.git

cd ../../srsRAN_Project
rm -rf build
mkdir build
cd build
cmake ../ -DENABLE_EXPORT=ON -DENABLE_ZEROMQ=ON
make -j$(nproc)