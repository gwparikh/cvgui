#!/usr/bin/python
"""Classes and functions for interactively visualizing trajectory data, particularly for optimizing configuration and training data."""

import os, sys, time, argparse, traceback
import mtostorage
import mtomoving
import cvgui, cvhomog, cvgeom
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
    def __init__(self, videoFilename, databaseFilename=None, homographyFilename=None, withIds=True, idFontScale=2.0, withBoxes=True, withFeatures=True, boxThickness=1, objTablePrefix='', drawFeatures=False, drawObjectFeatures=False, **kwargs):
        # construct cvPlayer object (which constructs cvGUI object)
        if 'name' not in kwargs:
            # add the databaseFilename to the name if not customized
            kwargs['name'] = "{} -- {}".format(videoFilename, databaseFilename)
        super(cvTrajOverlayPlayer, self).__init__(videoFilename=videoFilename, **kwargs)
        
        # trajectory overlay-specific properties
        self.databaseFilename = databaseFilename
        self.homographyFilename = homographyFilename
        self.withIds = withIds
        self.idFontScale = idFontScale
        self.withBoxes = withBoxes
        self.withFeatures = withFeatures
        self.boxThickness = boxThickness
        self.objTablePrefix = objTablePrefix
        self.drawFeatures = drawFeatures
        self.drawObjectFeatures = drawObjectFeatures
        
        # important variables and containers
        self.db = None
        self.hom = None
        self.invHom = None
        self.movingObjects = []
        self.features = []
        self.imgObjects = []
        self.selectedObjects = []
        
        # key/mouse bindings
        self.addKeyBindings(['B','Shift + B'], 'toggleBoundingBoxes', warnDuplicate=False)          # b - toggle bounding boxes
        self.addKeyBindings(['J','Shift + J'], 'joinSelected')                                      # J / Shift + J - join selected objects
        self.addKeyBindings(['X','Shift + X'], 'explodeSelected')                                   # X / Shift + X - explode selected objects
        self.addKeyBindings(['Ctrl + T'], 'saveObjects', warnDuplicate=False)                       # Ctrl + T - save annotated objects to table
    
    def open(self):
        """Open the video and database."""
        # open the database first (which also loads the homography and creates the image objects)
        # it will start loading trajectories in a separate process and return them as they are finished
        self.openDatabase()
        
        # open a window (which also sets up to read keys and mouse clicks) 
        self.openGUI()
        
        # open the video (which also sets up the trackbar)
        self.openVideo()
    
    # ### Methods for interacting with the database ###
    def openDatabase(self):
        """Open the database with the mtostorage.CVsqlite class, load in the objects,
           load the homography, and create an ImageObject for each object for working
           in image space."""
        if self.databaseFilename is not None and self.homographyFilename is not None:
            # read the homography if we have one
            print "Loading homography from file '{}'".format(self.homographyFilename)
            self.hom = np.loadtxt(self.homographyFilename)
            self.invHom = cvhomog.Homography.invertHomography(self.hom)
            print "Starting reader for on database '{}'".format(self.databaseFilename)
            withFeatures = self.withFeatures or self.withBoxes or self.drawFeatures or self.drawObjectFeatures
            self.db = mtostorage.CVsqlite(self.databaseFilename, objTablePrefix=self.objTablePrefix, withFeatures=withFeatures, homography=self.hom, invHom=self.invHom, withImageBoxes=self.withBoxes)
            if self.drawFeatures:
                self.db.loadFeaturesInThread()
            self.db.loadObjectsInThread()
            self.movingObjects, self.features = self.db.objects, self.db.features
            self.imgObjects = self.db.imageObjects
            print "Objects are now loading from the database in a separate thread"
            print "You may notice a slight delay in loading the objects after the video first starts."

    def saveObjects(self, key=None):
        self.saveObjectsToTable()

    def saveObjectsToTable(self, tablePrefix=None):
        """Save all of the objects to new tables (with the given tablePrefix) in the database."""
        tablePrefix = time.strftime("annotations_%d%b%Y_%H%M%S_") if tablePrefix is None else tablePrefix
        objList = []
        for o in self.imgObjects:
            objList.extend(o.getObjList())
        print "Saving {} objects with table prefix {}...".format(len(objList), tablePrefix)
        self.db.writeObjects(objList, tablePrefix)
        
    # ### Methods for rendering/playing annotated video frames ###
    def plotFeaturePoint(self, feat, i):
        """Plot the features that make up the object as points (with no historical trajectory)."""
        if feat.existsAtInstant(i):
            if not hasattr(feat, 'color'):
                feat.color = cvgui.randomColor()
            fp = mtomoving.getFeaturePositionAtInstant(feat, i, invHom=self.invHom)
            p = cvgeom.imagepoint(fp.x, fp.y, color=feat.color)
            self.drawPoint(p, pointIndex=False)
        
    def plotObjectFeatures(self, obj, i):
        """Plot the features that make up the object as points (with no historical trajectory)."""
        if len(obj.subObjects) > 0:
            for o in obj.subObjects:
                self.plotObjectFeatures(o, i)           # recurse into sub objects
        else:
            if obj.existsAtInstant(i) and obj.drawAsJoined(i):
                # if we are supposed to plot this object, get its features and plot them as points (but no historical trajectory)
                featPositions = obj.getFeaturePositionsAtInstant(i)             # gives us all the joined features as well
                
                # plot all the points
                for fp in featPositions:
                    p = cvgeom.imagepoint(fp.x, fp.y, color=obj.color)
                    self.drawPoint(p, pointIndex=False)                     # we would need to change a few things to get ID's, so we'll leave it out until we need it
    
    def plotObject(self, obj, endPos):
        """Plot the trajectory of the given object from it's beginning to endPos (i.e. 'now' in the
           video player). Also draws a bounding box if withBoxes is True."""
        self.db.update()
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
                            p = traj[i].asint()
                            b = p.astuple()
                            cv2.line(self.img, a, b, obj.color)         # TODO change this to use cvgui.drawObject (need to make trajectories into ImageLine objects)
                            
                        # print the ID at the last point we plotted (b) if requested
                        if self.withIds:
                            idStr = "{}".format(obj.getNum())
                            self.drawText(idStr, p.x, p.y, fontSize=self.idFontScale, color=obj.color, thickness=2)
                        
                        # draw the bounding box for the current frame if requested
                        selected = obj in self.selectedObjects
                        if self.withBoxes or selected:
                            box = obj.getBox(endPos)
                            if not box.isNone():
                                bth = 8*self.boxThickness if selected else self.boxThickness
                                cv2.rectangle(self.img, box.pMin.asint().astuple(), box.pMax.asint().astuple(), obj.color, thickness=bth)
                        
                        # also the features
                        if self.drawObjectFeatures:
                            self.plotObjectFeatures(obj, endPos)
            elif obj in self.selectedObjects:
                # if this object doesn't exist but is selected, remove it from the list
                self.deselectObject(obj)
    
    def drawFrame(self):
        # NOTE we are deliberately overriding cvgui's drawFrame to remove that functionality (creating points/geometric objects in an image) in exchange for new functionality (manipulating MovingObjects)
        # update objects from database reader
        self.db.update()
        if self.drawFeatures:
            self.drawFeaturePoints()
        else:
            self.drawMovingObjects()
    
    def drawFeaturePoints(self):
        """Add all features in the current frame to the image."""
        i = self.getVideoPosFrames()               # get the current frame number
        if i < self.nFrames - 1:
            for feat in self.features:
                self.plotFeaturePoint(feat, i)
    
    def drawMovingObjects(self):
        """Add annotations to the image, and show it in the player."""
        # go through each object to draw them on the image
        i = self.getVideoPosFrames()               # get the current frame number
        if i < self.nFrames - 1:
            for obj in self.imgObjects:
                self.plotObject(obj, i)
            
    # ### Methods for handling mouse input ###
    def drag(self, event, x, y, flags, param):
        # kill the drag method since it won't work
        pass
    
    def leftClickDown(self, event, x, y, flags, param):                         # we are overriding this method, which is bound by cvgui
        """Handle when the user left-clicks on the image."""
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
        self.update()
    
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
