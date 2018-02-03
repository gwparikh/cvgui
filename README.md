# cvgui

Python/OpenCV-based GUI tools for working with computer vision data. Includes scripts for:
  1. Selecting points or regions in an image file and saving them to a text configuration file (imageselector.py).
  2. Creating a homography from a camera frame and aerial image (homMaker.py).
  3. Playing a video with trajectory data overlaid on the image (cvplayer.py).
  4. Creating combination of datasets with a range of configurations (cfg_combination.py).
  5. Comparing combination of datasets (created using script 4) to find the best configuration for grouping features (compare.py).
  6. Use genetic algorithm to do comparison as script 5 but with faster speed and lower memory usage (genetic_compare.py).

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

### Creating combination of datasets with a range of configurations.
To create combination of datasets (sqlite(s)) with a range of configuration, run the command:
```
cfg_combination.py -o <homography_file> -d <database_file>  -t <range_configuration> -m <mask_file> <video_file>
```
Two folder (cfg_files and sql_files) will be created. All of the datasets (sqlite(s)) will be store in sql_files with a corresponding ID. Each ID of the sqlite has a corresponding configuration file store in cfg_files with the same ID. For example, the configuration produce sql_files/Sqlite_ID_28.sqltie is cfg_files/Cfg_ID_28.cfg.

Format of the range_configuration file is the extended version of the original configuration file that it accepts two or three inputs as the range of configuration.
```
config1 = 10 20 5
config2 = 10 20
```
The range of config1 is from 10 to 20 with steps of 5. The range of config2 is from 10 to 20 with steps of 1 (default step as 1).

Note:
  1. If the configuration file contains the range of configurations is not entered, it will be default as range.cfg.
  2. If database file is not entered, trajextract.py will be used to create a database file and cvplayer.py will be used to create annotation.  
  3. Mask file is recommended to improve accuracy.

### Comparing combination of datasets to find the best configuration for grouping features (not recommended)
To compare all of the data sets that are created by cfg_combination.py, run the command:
```
compare.py -o <homography_file> -d <database_file> -f <first_ID> -l <last_ID> -m <matching_distance>
```
A graph will be created to show all IDs and their accuracy score. Best accuracy ID will be contained in the title of the graph and it will be display as a red dot in the graph. Configuration with the best accuracy ID is the best configuration for grouping features in the video.
Note:
  1. If matching_distance is not entered, it will be default as 10.
  2. Since it's using brute force implementation, best configuration is guaranteed but the runtime of the program is very slow and it uses lots of memory.
  
### Use genetic algorithm to compare combination of datasets to find the best configuration for grouping features. (recommended)
To compare all of the data sets that are created by cfg_combination.py (with genetic algorithm), run the command:
```
genetic_compare.py -o <homography_file> -d <database_file> -f <first_ID> -l <last_ID> -m <matching_distance> -p <population> -a <accuracy> -np <number_of_parents>
```
A graph will be created to show all IDs and their accuracy score. Best accuracy ID will be contained in the title of the graph and it will be display as a red dot in the graph. Configuration with the best accuracy ID is the best configuration for grouping features in the video.

Note:
  1. If matching_distance is not entered, it will be default as 10.
  2. Population, accuracy and number_parents are parameter for genetic algorithm.
  3. Population determine the number of individuals that are initialized at the beginning.
  4. Accuracy determine when to terminate program (number of steps with no improvement).
  5. Number of parents determine the number of parents to select from population each generation.
  6. Program might not give the best configuration depending on the parameters (see note 2-5).
