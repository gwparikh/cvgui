#!/usr/bin/python
"""Classes for taking input from images, based on the cvgui module."""

import os, sys, time, argparse, traceback
import rlcompleter, readline
import numpy as np
import threading
import cvgui

class imagepoint(object):
    """A class representing a point selected on an image."""
    def __init__(self, x, y, index=None):
        self.x, self.y = x, y
        self.index = index
    
    def __repr__(self):
        return "<imagepoint {}: ({}, {})>".format(self.index, self.x, self.y)
        
    def asTuple(self):
        return (self.x, self.y)
    
    def asList(self):
        return [self.x, self.y]
        
    def move(self, x, y):
        self.x += x
        self.y += y
        
    def update(self, p):
        self.x = p.x
        self.y = p.y
        
    def rotate(self, o, dPhi):
        rho, phi = rabutils.cart2pol(self.x-o.x, self.y-o.y)
        self.x, self.y = rabutils.pol2cart(rho, phi + dPhi)
        
    def dist(self, p):
        """Calculates the distance between points self and p."""
        return math.sqrt((self.x-p.x)**2 + (self.y-p.y)**2)

class ImageInput(cvgui.cvImage):
    """A class for taking input from images displayed using OpenCV's highgui features.
    """
    def __init__(self, imageFilename, name=None, printKeys=False, printMouseEvents=None):
        # construct cvGUI object
        super(ImageInput, self).__init__(imageFilename=imageFilename, name=name, printKeys=printKeys, printMouseEvents=printMouseEvents)
        
        # ImageInput-specific properties
        self.pointFilename = pointFilename
        self.clickStart = imagepoint(None, None)
        
        # key/mouse bindings
        # self.keyBindings[<code>] = 'fun'                  # method 'fun' must take key code as only required argument
        # self.mouseBindings[<event code>] = 'fun'          # method 'fun' must take event, x, y, flags, param as arguments
        
    def open(self):
        """Open a window and image file and load the point config."""
        self.openWindow()
        self.openImage()
        
    def loadPoints(self):
        """Loads the point configuration file (list of corresponding points)."""
        # look for the image file basename in the file
        if self.imageBasename in self.pointConfig:
            # if we found it, load the points in this section
            for i, p in self.pointConfig[self.imageBasename].iteritems():
                try:
                    indx = int(i)
                    self.points[indx] = imagepoint(indx, map(float, p))
                except:
                    print "An error was encountered while processing the configuration file {}. Please check the formatting.".format(self.pointFilename)
                    break
    
    def savePoints(self):
        """Saves the list of points into the config file provided."""
        # clear the old section
        self.pointConfig[self.imageBasename] = {}
        
        # fill it with new points
        for i, p in self.points.iteritems():
            self.pointConfig[self.imageBasename][str(i)] = p.asList()
        
        # write the changes
        self.pointConfig.write()
        
    def drawFrame(self):
        """Show the image in the player."""
        cv2.imshow(self.windowName, self.img)
        
    def mouseMove(self, event, x, y, flags, param):
        if event == cv2.EVENT_MOUSEMOVE:
            # if left button is down and a point is not selected move the corner of the rectangle (or start it if first move w/ button down)
            
            # if one or more points is selected, drag it/them to move them
            pass
        
        
    def leftClick(self, event, x, y, flags, param):
        """Handle a left click on the image by doing one of the following:
            + Create a new point by clicking on the image
            + Select an existing point by clicking on it (within the clickThreshold)
            + Select multiple existing points by clicking and dragging
        """
        if event == cv2.EVENT_LBUTTONDOWN:
            # left button down, set the first point, select closest point within clickThreshold if there is one
            pass
        elif event == cv2.EVENT_LBUTTONUP:
            # left button up, if (x,y) is same as first point, stop after selecting point
            
            # if it's different, select all points within the region selected (created by first point and this point)
            
            pass
            
        # redraw image
        self.clearFrame()
        self.drawFrame()
       