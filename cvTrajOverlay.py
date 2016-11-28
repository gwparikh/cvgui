#!/usr/bin/python
"""Classes and functions for interactively visualizing trajectory data, particularly for optimizing configuration and training data."""

import os, sys, time, argparse, traceback
import mtostorage
import mtomoving
import cvgui
import cvutils
import random
import rlcompleter, readline
import cv2
import numpy as np
import threading

class ObjectJoiner(cvgui.action):
    """An action for joining a list of objects."""
    def __init__(self, objList):
        self.objList = list(objList)                    # make a copy of the list so they can change the selected objects outside of here
        self.objNums = [o.getNum() for o in self.objList]
        self.name = "{}".format(self.objNums)           # name is numbers of objects being joined (used in __repr__)
        
    def do(self):
        """Join all objects in the list by cross-joining all objects."""
        for o1 in self.objList:
            for o2 in self.objList:
                if o1.getNum() != o2.getNum():
                    o1.join(o2)
    
    def undo(self):
        """Undo the join by cross-unjoining all objects."""
        for o1 in self.objList:
            for o2 in self.objList:
                if o1.getNum() != o2.getNum():
                    o1.unjoin(o2)
    
class ObjectExploder(cvgui.action):
    """An action for joining a list of objects."""
    def __init__(self, objList):
        self.objList = list(objList)                    # make a copy of the list so they can change the list outside of here
        self.objNums = [o.getNum() for o in self.objList]
        self.name = "{}".format(self.objNums)           # name is numbers of objects being exploded (used in __repr__)
        
    def do(self):
        """Explode all objects in the list exploding each objects."""
        for o in self.objList:
            o.explode()
    
    def undo(self):
        """Undo the explode by unexploding each object."""
        for o in self.objList:
            o.unExplode()
    
class cvTrajOverlayPlayer(cvgui.cvPlayer):
    """A class for playing a video with trajectory data overlayed on the image.
       Based on the cvPlayer class, which handles reading the video file and
       playing the video frames, and the cvGUI class, which handles mouse and
       keyboard input to the window and maintains an 'undo/redo buffer' (with
       undo bound to Ctrl+Z and redo bound to Ctrl+Y/Ctrl+Shift+Z) to allow
       actions to be easily done/undone/redone."""
    def __init__(self, videoFilename, databaseFilename=None, homographyFilename=None, fps=15.0, name=None, printKeys=False, printMouseEvents=None, withIds=True, idFontScale=2.0, withBoxes=True, boxThickness=1, objTablePrefix=''):
        # construct cvPlayer object (which constructs cvGUI object)
        name = "{} -- {}".format(videoFilename, databaseFilename) if name is not None else name         # add the databaseFilename to the name if not customized
        super(cvTrajOverlayPlayer, self).__init__(videoFilename=videoFilename, fps=fps, name=name, printKeys=printKeys, printMouseEvents=printMouseEvents)
        
        # trajectory overlay-specific properties
        self.databaseFilename = databaseFilename
        self.homographyFilename = homographyFilename
        self.withIds = withIds
        self.idFontScale = idFontScale
        self.withBoxes = withBoxes
        self.boxThickness = boxThickness
        self.objTablePrefix = objTablePrefix
        
        # important variables and containers
        self.db = None
        self.hom = None
        self.invHom = None
        self.objects = []
        self.features = []
        self.imgObjects = []
        self.selectedObjects = []
        
        # key/mouse bindings
        # self.mouseBindings[<event code>] = 'fun'          # method 'fun' must take event, x, y, flags, param as arguments
        # self.keyBindings[<code>] = 'fun'                  # method 'fun' must take key code as only required argument
        
        # default bindings:
        self.addMouseBindings([cv2.EVENT_LBUTTONDOWN], 'leftClick')             # left click - select/deselect/multi-select objects for manipulation
        self.addKeyBindings([98,1048674], 'toggleBoundingBoxes')                # b - toggle bounding boxes
        self.addKeyBindings([106,65610,1048682,1114186], 'joinSelected')        # J / Shift + J - join selected objects
        self.addKeyBindings([120,65624,1048696,1114200], 'explodeSelected')     # X / Shift + X - explode selected objects
    
    def open(self):
        """Open the video and database."""
        # open a window (which also sets up to read keys and mouse clicks) and the video (which also sets up the trackbar) and the database (which also loads the homography and creates the image objects)
        self.openWindow()
        self.openVideo()
        self.openDatabase()
    
    # ### Methods for interacting with the database ###
    def openDatabase(self):
        """Open the database with the mtostorage.CVsqlite class, load in the objects,
           load the homography, and create an ImageObject for each object for working
           in image space."""
        if self.databaseFilename is not None and self.homographyFilename is not None:
            # read the homography if we have one
            self.hom = np.loadtxt(self.homographyFilename)
            self.invHom = cvgui.invertHomography(self.hom)
            self.db = mtostorage.CVsqlite(self.databaseFilename, withFeatures=True)
            self.db.loadObjects(objTablePrefix=self.objTablePrefix)
            self.objects, self.features = self.db.objects, self.db.features
            self.imgObjects = []
            for o in self.objects:
                self.imgObjects.append(mtomoving.ImageObject(o, self.hom, self.invHom))
    
    def saveObjectsToTable(self, tablePrefix):
        """Save all of the objects to new tables (with the given tablePrefix) in the database."""
        objList = []
        for o in self.objects:
            objList.extend(o.getObjList())
        self.db.writeObjects(objList, tablePrefix)
        
    # ### Methods for rendering/playing annotated video frames ###
    def plotObjectFeatures(self, obj, i):
        # TODO plot object features as points (circles) or something
        pass
    
    def plotObject(self, obj, endPos):
        """Plot the trajectory of the given object from it's beginning to endPos (i.e. 'now' in the
           video player). Also draws a bounding box if withBoxes is True."""
        if len(obj.subObjects) > 0:
            # if this object has sub objects, plot those instead (recursing)
            for o in obj.subObjects:
                self.plotObject(o, endPos)
        else:
            # otherwise plot this object
            if obj.existsAtInstant(endPos):
                if obj.drawAsJoined(endPos):
                    # get the object trajectory up to this point
                    traj = obj.toInstant(endPos)
                    
                    if obj.color is None:
                        # pick a random color if we don't already have one
                        obj.color = cvgui.randomColor()
                    
                    # plot it on the image as a series of line segments
                    if len(traj) > 1:
                        for i in range(1, len(traj)):
                            a = traj[i-1].asint().astuple()
                            b = traj[i].asint().astuple()
                            cv2.line(self.frameImg, a, b, obj.color)
                            
                        # print the ID at the last point we plotted (b) if requested
                        if self.withIds:
                            # Fonts: cv2.cv. : FONT_HERSHEY_SIMPLEX, FONT_HERSHEY_PLAIN, FONT_HERSHEY_DUPLEX, FONT_HERSHEY_COMPLEX, FONT_HERSHEY_TRIPLEX, FONT_HERSHEY_COMPLEX_SMALL, FONT_HERSHEY_SCRIPT_SIMPLEX, FONT_HERSHEY_SCRIPT_COMPLEX [ + FONT_ITALIC]
                            idStr = "{}".format(obj.getNum())
                            cv2.putText(self.frameImg, idStr, b, cv2.cv.CV_FONT_HERSHEY_PLAIN, self.idFontScale, obj.color, thickness=2)
                            
                        # draw the bounding box for the current frame if requested
                        selected = obj in self.selectedObjects
                        if self.withBoxes or selected:
                            box = obj.getBox(endPos)
                            bth = 8*self.boxThickness if selected else self.boxThickness
                            cv2.rectangle(self.frameImg, box.pMin.asint().astuple(), box.pMax.asint().astuple(), obj.color, thickness=bth)
            elif obj in self.selectedObjects:
                # if this object doesn't exist but is selected, remove it from the list
                self.deselectObject(obj)
        
    def drawFrame(self):
        """Add annotations to the image, and show it in the player."""
        # go through each object to draw them on the image
        i = self.getVideoPosFrames()               # get the current frame number
        if i < self.nFrames - 1:
            for obj in self.imgObjects:
                self.plotObject(obj, i)
            # show the image
            cv2.imshow(self.windowName, self.frameImg)
            
    # ### Methods for handling mouse input ###
    def leftClick(self, event, x, y, flags, param):
        """Handle when the user left-clicks on the image."""
        if event == cv2.EVENT_LBUTTONDOWN:
            # left button down, select (or deselect) the object at this point
            clickedOnObject = None
            for obj in self.imgObjects:
                if len(obj.subObjects) > 0:
                    for o in obj.subObjects:
                        if o.isInBox(self.posFrames, x, y):
                            # this (sub-)object, select it (or add it to the selected objects)
                            clickedOnObject = o
                            break
                elif obj.isInBox(self.posFrames, x, y):
                    # this object, select it (or add it to the selected objects)
                    clickedOnObject = obj
                    break
            # clear selected if no modifiers
            if flags >= 32:
                flags -= 32         # hack to work around hermes alt flag issue
            if flags == 0:
                self.deselectAll()
            if clickedOnObject is not None:
                self.toggleSelected(clickedOnObject, flags)
                
            # redraw image
            self.clearFrame()
            self.drawFrame()
        
    # ### Methods for selecting/deselecting objects in the player
    def selectObject(self, obj):
        """Select an object by adding it to the selectedObjects list."""
        if obj not in self.selectedObjects:
            self.selectedObjects.append(obj)
    
    def deselectObject(self, obj):
        """Deselect an object by removing it from the selectedObjects list."""
        if obj in self.selectedObjects:
            self.selectedObjects.pop(self.selectedObjects.index(obj))
        
    def toggleSelected(self, obj, flags):
        """Toggle the selected/deselectd state of an object."""
        # currently, ctrl, shift, or any modifier activates multi-select, could do something different by checking flags
        if obj in self.selectedObjects:
            # if it's selected, remove it
            self.deselectObject(obj)
        else:
            # if it's not selected, select it
            self.selectObject(obj)

    def deselectAll(self):
        """Deselect all objects by clearing the selectedObjects list."""
        self.selectedObjects = []
        
    # ### Methods for handling keyboard input ###
    def toggleBoundingBoxes(self, key):
        """Turn display of bounding boxes around the objects on/off."""
        self.withBoxes = not self.withBoxes
        
    # ### Methods for joining/exploding objects (using actions so they can be undone/redone) ###
    def joinSelected(self, key):
        """Join the selected objects."""
        # create an ObjectJoiner object with the current list of selected objects
        a = ObjectJoiner(self.selectedObjects)
        
        # call our do() method (inherited from cvGUI) with the action so it can be undone
        self.do(a)
        
        # update the list of selected objects to reflect only the object that represents the joined objects
        self.selectedObjects = [o for o in self.selectedObjects if o.drawAsJoined(self.getVideoPosFrames())]
    
    def explodeSelected(self, key):
        """Explode the selected objects."""
        # create an ObjectExploder object with the current list of selected objects
        a = ObjectExploder(self.selectedObjects)
        
        # call our do() method (inherited from cvGUI) with the action so it can be undone
        self.do(a)
