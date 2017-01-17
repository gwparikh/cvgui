#!/usr/bin/python

"""Classes and methods for calibrating object tracking."""

import os, sys, time, argparse, traceback
import mtostorage
import mtomoving
import cvgui, cvhomog, cvgeom
import random
import rlcompleter, readline
import cv2
import numpy as np
import threading

class FeatureTargetMaker(cvgui.cvPlayer):
    """A class for creating video frame annotations for calibrating feature tracking."""
    # most of our methods will come from cvGUI, but we will change slightly the functionality of (so far) one method
    def createBox(self):
        """Create a box in the image with a unique name that corresponds to the frame number."""
        boxFrame = self.getVideoPosFrames()           # get the frame number
        
        # run through the boxes we have already to make sure we don't overlap
        bn = 0              # start with box 0 in this frame
        boxIndex = "{}_{}".format(boxFrame, bn)
        while boxIndex in self.objects:
            bn += 1
            boxIndex = "{}_{}".format(boxFrame, bn)
        
        print "Starting box {}".format(boxIndex)
        self.creatingObject = cvgeom.imagebox(boxIndex)
        self.creatingObject.select()
        self.update()
    