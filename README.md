# cvgui

Python/OpenCV-based GUI tools for working with computer vision data. Includes scripts for:
  1. Selecting points or regions in an image file and saving them to a text configuration file (imageselector.py).
  2. Creating a homography from a camera frame and aerial image (homMaker.py).
  3. Playing a video with trajectory data overlaid on the image (cvplayer.h).

These scripts are based on the cvgui class, which handles the capturing of keyboard and mouse input, displaying images, and running on a fixed frame rate. This class is used as the base class for video player and image viewer classes, which are then used by the scripts mentioned above.

cvplayer.py uses trajectory data extracted from [TrafficIntelligence](https://bitbucket.org/Nicolas/trafficintelligence/wiki/Home), along with some modules provided by the MTO's cvtools package for loading and manipulating trajectory data (URL coming soon...).


## Instructions for using scripts
Documentation for each of the command line options accepted/required by these scripts can be viewed by executing ```<script_name>.py -h```, e.g.: ```imageselector.py -h```.

### Selecting points in an image.
To create a text file with regions and points selected in an image, use the command:
```
imageselector.py -f <config_file> <image_file>
```
where configfile is the name of the text configuration file (any extension) and imagefile is the name of the image file (png or jpg, perhaps others).

To select points, double-click in a location on the image. To create a region, type the 'r' key, then start clicking to outline a region. Clicking on the first point will close the region. To save the points in the file, press ```Ctrl+T```. To undo press ```Ctrl+Z```, to redo press ```Ctrl+Shift+Z``` or ```Ctrl+Y```.

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
