# cvgui

Python/OpenCV-based GUI tools for working with computer vision data produced by [TrafficIntelligence](https://bitbucket.org/Nicolas/trafficintelligence/wiki/Home). Includes scripts for:
  1. Selecting points or regions in an image or video file and saving them to a text configuration file (imageselector.py and videoselector.py).
  2. Creating a homography from a camera frame and aerial image (homMaker.py).
  3. Playing a video with trajectory data overlaid on the image (cvplayer.py).
  4. Calibrating the feature grouping parameter with the genetic algorithm (grouping calibration.py)

These scripts are based on the cvgui class, which handles the capturing of keyboard and mouse input, displaying images, and running on a fixed frame rate. This class is used as the base class for video player and image viewer classes, which are then used by the scripts mentioned above. While some components work by themselves, note that (3)-(7) require that TrafficIntelligence is installed and present in your PYTHONPATH.

Note that currently the master branch is written for Python 2. Python 3 support is available for many of the tools in the 'python3' branch (Python 3 support for the configuration optimization tools is still in progress). Note that both versions support both OpenCV 2 and 3.

## Experimental Scripts
In addition to the tools described above, some experimental work can be found in the following files:
- __videowatcher.py__: Script for "watching" a video file by calculating the peak signal-to-noise (PSNR) and structural similarity index (SSIM) between successive frames to find irregularities.
- __featuretracker.py__: Implementation of the feature tracking algorithm (optimized for tracking vehicles from low camera angles) described [in this paper](cecas.clemson.edu/~stb/publications/vehicle_tracking_its2008.pdf).

Note that these files may or may not work at any given time.

## Instructions for using scripts
Documentation for each of the command line options accepted/required by these scripts can be viewed by executing ```<script_name>.py -h```, e.g.: ```imageselector.py -h```.

### Selecting points in an image.
To create a text file with regions and points selected in an image, use the command:
```
imageselector.py -f <config_file> <image_file>
```
where configfile is the name of the text configuration file (any extension) and imagefile is the name of the image file (png or jpg, perhaps others).

To select points, double-click in a location on the image. To create a region, type the 'r' key, then start clicking to outline a region. Clicking on the first point will close the region. To save the points in the file, press ```Ctrl+T```. To undo press ```Ctrl+Z```, to redo press ```Ctrl+Shift+Z``` or ```Ctrl+Y```. Points and regions can be moved by clicking and dragging on them.

### Creating a homography
To start the homography creator, run the command:
```
homMaker.py -w <aerial_image> -i <camera_frame> -u <units_per_pixel> -f <config_file>
```

The two image files will then open in separate windows. Select corresponding points in the images by double-clicking. Once you have clicked at least 4 points in the image, the homography will be computed. You may continue adding points to increase the quality of the homography (to a limit). To recalculate the homography, press ```Ctrl+R```. To save the
points in the config file, press ```Ctrl+T```. To output a homography to a single file named homography.txt, press ```Ctrl+Shift+H```.


### Playing a video
To play a video with trajectory data from an sqlite (TrafficIntelligence) database, run the command:
```
cvplayer.py -d <database_file> -o <homography_file> <video_file>
```
You can pause by hitting the spacebar, advance/reverse with Ctrl+Right/Ctrl+Left, and quit with Ctrl + Q. There are also other features for manipulating the object data that will be documented further in the future.

A note about the video control: due to a bug in the OpenCV Python interface, video seeking does not work correctly. To work around this, I have implemented my own video seeking, however it is primitive and fairly slow (especially for reversing, since it has to back up to the start). This may be fixed at some point in OpenCV, or I may reimplement this all in C++, which I believe does not show the same issue. For now though, try to limit your skipping (at least it works at all, unlike everything we've had before) and use short videos to reduce your frustration.


### Use genetic algorithm to search for good tracking configurations
This script is using genetic algorithm to search for good tracking configuration (Basically it does both initialization and comparison with genetic algorithm).
To use this script run:
```
grouping_calibration.py -o <homography_file> -d <database_file> -t <range_configuration> -m <mask_file> -p <population> -a <accuracy> -np <number_of_parents> -md <matching_distance> <inputVideo>
```

  Note:
  1. If the configuration file contains the range of configurations is not entered, it will be default as range.cfg.
  2. If database file is not entered, trajextract.py will be used to create a database file and cvplayer.py will be used to create annotation.  
  3. Mask file is recommended to improve accuracy.
  4. For all configurations that are used for feature tracking should have the same value in both configuration files.
  5. If matching_distance is not entered, it will be default as 10.
  6. Population, accuracy and number_parents are parameter for genetic algorithm.
  7. Population determine the number of individuals that are initialized at the beginning.
  8. Accuracy determine when to terminate program (number of steps with no improvement).
  9. Number of parents determine the number of parents to select from population each generation.
  10. Parameter ```-p 5 -a 4 -np 4``` is good for around 100 combinations of configurations.
  
  Other Calibration tools:
  1. calibCreateAll.py (which will create all combinations of configurations along with their trajectories)
  2. calibBruteforceSearch.py (which search through all trajectories files to find the best configuration with brute force)
  3. calibGeneticSearch.py (which search through all trajectories files to find the best configuration with genetic algorithm)
