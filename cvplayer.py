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
    parser.add_argument('-t', dest='objTablePrefix', default='', help="Prefix to append to the objects_features table when loading objects from the database (for loading cleaned or otherwise-manipulated object data).")
    parser.add_argument('-o', dest='homographyFilename', help="Name of the file containing the homography (for projecting trajectory data between image space and world space).")
    parser.add_argument('-pk', dest='printKeys', action='store_true', help="Print keys that are read from the video window (useful for adding shortcuts and other functionality).")
    parser.add_argument('-pm', dest='printMouseEvents', type=int, nargs='*', help="Print mouse events that are read from the video window (useful for adding other functionality). Optionally can provide a number, which signifies the minimum event flag that will be printed.")
    parser.add_argument('-f', dest='fps', type=float, default=15.0, help="Framerate for video playback (default: %(default)s).")
    parser.add_argument('-i', dest='interactive', action='store_true', help="Play the video in a separate thread and start an interactive shell.")
    parser.add_argument('-no', dest='noOverlay', action='store_true', help="Just play the video, don't add any overlay.")
    parser.add_argument('-nb', dest='noBoxes', action='store_true', help="Don't add bounding boxes.")
    parser.add_argument('-nf', dest='noFeatures', action='store_true', help="Don't load features from the database, only objects.")
    args = parser.parse_args()
    videoFilename = args.videoFilename
    databaseFilename = args.databaseFilename
    homographyFilename = args.homographyFilename
    objTablePrefix = args.objTablePrefix
    fps = args.fps
    withBoxes = not args.noBoxes
    withFeatures = not args.noFeatures
    printMouseEvents = None
    if args.printMouseEvents is not None:
        if len(args.printMouseEvents) == 0:
            printMouseEvents = 0
        elif len(args.printMouseEvents) > 0:
            printMouseEvents = args.printMouseEvents[0]
    
    if cvtoolsAvailable and not args.noOverlay:
        player = cvTrajOverlay.cvTrajOverlayPlayer(videoFilename, databaseFilename=databaseFilename, homographyFilename=homographyFilename, fps=fps, printKeys=args.printKeys, printMouseEvents=printMouseEvents, withBoxes=withBoxes, withFeatures=withFeatures, objTablePrefix=objTablePrefix)
    else:
        player = cvgui.cvPlayer(videoFilename, fps=fps, printKeys=args.printKeys, printMouseEvents=printMouseEvents)
    
    if args.interactive:
        player.playInThread()
        # once the video is playing, make this session interactive
        os.environ['PYTHONINSPECT'] = 'Y'           # start interactive/inspect mode (like using the -i option)
        readline.parse_and_bind('tab:complete')     # turn on tab-autocomplete
    else:
        player.play()
    