#!/bin/bash

# Script for compiling OpenCV on a new Ubuntu installation. Requires root access.
OPENCV_LATEST=3.4.1

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
sudo apt-get -y install build-essential make cmake python3-dev python3-pip

# download opencv
echo "Downloading OpenCV $OPENCV_LATEST ..."
wget -O opencv-$OPENCV_LATEST.zip https://github.com/opencv/opencv/archive/$OPENCV_LATEST.zip

# install opencv
echo "Installing OpenCV $OPENCV_LATEST ..."
unzip opencv-$OPENCV_LATEST.zip
cd opencv-$OPENCV_LATEST
mkdir build
cd build
cmake -D CMAKE_BUILD_TYPE=RELEASE -D CMAKE_INSTALL_PREFIX=/usr/local .. && make -j $(nproc) && sudo make install
echo '/usr/local/lib' | sudo tee /etc/ld.so.conf.d/opencv.conf > /dev/null 2>&1
sudo ldconfig

echo "Installation complete!"
