#!/bin/bash

# Script for compiling OpenCV 2.4 on a new Ubuntu installation

echo "Updating ..."
sudo apt-get update
sudo apt-get -y upgrade
sudo apt-get -y dist-upgrade

# ffmpeg and associated libraries from the Ubuntu Repository 
# NOTE: This will need to be undone if you want to build your own ffmpeg, which would be recommended if you experience any problems loading or saving video
# but the version in the repository should work most of the time so this will suffice
echo "Installing FFMPEG from Ubuntu repository ..."
sudo apt-get -y install ffmpeg libavcodec-ffmpeg56 libavcodec-dev libavdevice-ffmpeg56 libavdevice-dev libavfilter-ffmpeg5 libavfilter-dev libavresample-ffmpeg2 libavresample-dev libavutil-ffmpeg54 libavutil-dev libswresample-ffmpeg1 libswresample-dev libswscale-ffmpeg3 libswscale-dev libxine2-ffmpeg libxine2-dev libgtk2.0-dev pkg-config

# install build tools
echo "Installing build tools ..."
sudo apt-get -y install build-essential make cmake python-dev python-pip

# install Python packages
echo "Installing scientific Python packages ..."
sudo apt-get -y install libgeos-dev python-numpy python-scipy python-shapely python-scikits-learn python-matplotlib python-putil

# download opencv
echo "Downloading OpenCV 2.4 ..."
wget -O opencv-2.4.13.zip https://github.com/Itseez/opencv/archive/2.4.13.zip

# install opencv
echo "Installing OpenCV 2.4 ..."
unzip opencv-2.4.13.zip
cd opencv-2.4.13
mkdir build
cd build
cmake -D CMAKE_BUILD_TYPE=RELEASE -D CMAKE_INSTALL_PREFIX=/usr/local .. && make -j $(nproc) && sudo make install
echo '/usr/local/lib' | sudo tee /etc/ld.so.conf.d/opencv.conf > /dev/null 2>&1
sudo ldconfig

echo "Installation complete!"
