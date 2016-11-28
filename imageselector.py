#!/usr/bin/python
"""A script for running a cvTrajOverlay player with a video, and optionally adding overlay from database of trajectory data.."""

import os, sys, time, argparse, traceback
import rlcompleter, readline
import numpy as np
import threading
import cvgui

cvtoolsAvailable = False
try:
    import cvTrajOverlay
    cvtoolsAvailable = True
except ImportError as e:
    print "Error importing cvTrajOverlay module: {}".format(e.message)
    print "Use of trajectory data is not available. This is likely because the mto-cvtools package has not been installed."
    print "See <URL-TBD> for more details..."

# Entry point
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Video player for interactively visualizing trajectory data. Requires the mto-cvtools package ('cvtools' module) for loading and manipulating trajectory data, otherwise only plays the video. This executable is provided with cvgui, a Python module for easy implementation of graphical interfaces for working with video or images..")
    parser.add_argument('videoFilename', help="Name of the video file to play.")
    parser.add_argument('-d', dest='databaseFilename', help="Name of the database (sqlite file) containing trajectory data.")
    parser.add_argument('-t', dest='objTablePrefix', help="Prefix to append to the objects_features table when loading objects from the database (for loading cleaned or otherwise-manipulated object data).")
    parser.add_argument('-o', dest='homographyFilename', help="Name of the file containing the homography (for projecting trajectory data between image space and world space).")
    parser.add_argument('-pk', dest='printKeys', action='store_true', help="Print keys that are read from the video window (useful for adding shortcuts and other functionality).")
    parser.add_argument('-pm', dest='printMouseEvents', type=int, nargs='*', help="Print mouse events that are read from the video window (useful for adding other functionality). Optionally can provide a number, which signifies the minimum event flag that will be printed.")
    parser.add_argument('-f', dest='fps', type=float, default=15.0, help="Framerate for video playback (default: %(default)s).")
    parser.add_argument('-i', dest='interactive', action='store_true', help="Play the video in a separate thread and start an interactive shell.")
    args = parser.parse_args()
    videoFilename = args.videoFilename
