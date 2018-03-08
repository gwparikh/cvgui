#!/usr/bin/python
"""Classes and functions for interactively visualizing trajectory data, particularly for optimizing configuration and training data."""

import os, sys, time, traceback
import numpy as np
import cv2
import cvgui, cvhomog, cvgeom
from . import trajstorage, cvmoving

class ObjectJoiner(cvgui.action):
    """An action for joining a list of objects."""
    def __init__(self, objList, drawObjectList):
        self.objList = list(objList)                    # make a copy of the list so they can change the selected objects outside of here
        self.drawObjectList = list(drawObjectList)
        self.objNums = [o.getNum() for o in self.objList]
        self.name = "{}".format(self.objNums)           # name is numbers of objects being joined (used in __repr__)
        
    def do(self):
        """Join all objects in the list by cross-joining all objects."""
        # join all the objects
        for o1 in self.objList:
            for o2 in self.objList:
                if o1.getNum() != o2.getNum():
                    print "joining {} & {}".format(o1.getNum(),o2.getNum())
                    o1.join(o2)
        # go through the joined objects to update the image objects
        for io, mo in zip(self.objList, self.drawObjectList):
            if io.drawAsJoined():
                # replace drawObject's properties with new ones
                tint = io.getTimeInterval()
                mo.replace(firstInstant=tint.first, lastInstant=tint.last, objects=io.imgBoxes)
                mo.hidden = False
            else:
                mo.hidden = True
    
    def undo(self):
        """Undo the join by cross-unjoining all objects."""
        for o1 in self.objList:
            for o2 in self.objList:
                if o1.getNum() != o2.getNum():
                    o1.unjoin(o2)
        # go through the joined objects to update the image objects
        for io, mo in zip(self.objList, self.drawObjectList):
            if io.drawAsJoined():
                # replace drawObject's properties with new ones
                tint = io.getTimeInterval()
                mo.replace(firstInstant=tint.first, lastInstant=tint.last, objects=io.imgBoxes)
            mo.hidden = False

class ObjectExploder(cvgui.action):
    """An action for joining a list of objects."""
    def __init__(self, objList, drawObjectList):
        self.objList = list(objList)                    # make a copy of the list so they can change the list outside of here
        self.drawObjectList = list(drawObjectList)
        self.objNums = [o.getNum() for o in self.objList]
        self.name = "{}".format(self.objNums)           # name is numbers of objects being exploded (used in __repr__)
        
    def do(self):
        """Explode all objects in the list exploding each objects."""
        for o in self.objList:
            o.explode()
        for o in self.drawObjectList:
            o.hidden = True
    
    def undo(self):
        """Undo the explode by unexploding each object."""
        for o in self.objList:
            o.unExplode()
        for o in self.drawObjectList:
            o.hidden = False

class ObjectDeleter(cvgui.action):
    """An action for deleting an object."""
    def __init__(self, objList, drawObjectList):
        self.objList = list(objList)                    # make a copy of the list so they can change the list outside of here
        self.drawObjectList = list(drawObjectList)
        self.objNums = [o.getNum() for o in self.objList]
        self.name = "{}".format(self.objNums)           # name is numbers of objects being exploded (used in __repr__)
        
    def do(self):
        """
        Delete all objects in the list by setting their isDeleted attribute to
        true.
        """
        for o in self.objList:
            o.isDeleted = True
        for o in self.drawObjectList:
            o.hidden = True
        
    def undo(self):
        """Undo the deletion by setting the isDeleted attribute to False."""
        for o in self.objList:
            o.isDeleted = False
        for o in self.drawObjectList:
            o.hidden = False

class FeatureGrouper(cvgui.action):
    """An action for grouping a list of features to create an object."""
    def __init__(self, obj, featList, hom, invHom, drawObjectList):
        self.obj = obj
        self.featList = featList
        self.hom = hom
        self.invHom = invHom
        self.drawObjectList = drawObjectList
        self.oId = None
        self.subObj = None
        self.name = "{}".format(self.featList)
    
    def do(self):
        self.oId, self.subObj = self.obj.groupFeatures(self.featList)
        self.drawObjectList[self.oId] = cvgeom.PlaneObjectTrajectory.fromImageObject(self.subObj)
    
    def undo(self):
        if self.oId is not None:
            self.obj._dropSubObject(self.oId)
            if self.oId in self.drawObjectList:
                del self.drawObjectList[self.oId]

class ObjectFeaturePoint(cvgeom.imagepoint):
    def __init__(self, objectId=None, **kwargs):
        super(ObjectFeaturePoint, self).__init__(**kwargs)
        self.objectId = objectId
    
    
class cvTrajOverlayPlayer(cvgui.cvPlayer):
    """A class for playing a video with trajectory data overlayed on the image.
       Based on the cvPlayer class, which handles reading the video file and
       playing the video frames, and the cvGUI class, which handles mouse and
       keyboard input to the window and maintains an 'undo/redo buffer' (with
       undo bound to Ctrl+Z and redo bound to Ctrl+Y/Ctrl+Shift+Z) to allow
       actions to be easily done/undone/redone."""
    def __init__(self, videoFilename, databaseFilename=None, homographyFilename=None, withIds=True, idFontScale=2.0, withBoxes=True, withFeatures=None, boxThickness=1, objTablePrefix='', enableDrawAllFeatures=False, drawAllFeatures=False, drawObjectFeatures=False, useAnnotations=False, **kwargs):
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
        self.withFeatures = withFeatures if withFeatures is not None else True
        self.boxThickness = boxThickness
        self.objTablePrefix = objTablePrefix
        self.enableDrawAllFeatures = enableDrawAllFeatures or drawAllFeatures
        self.drawAllFeatures = drawAllFeatures
        self.drawObjectFeatures = drawObjectFeatures
        self.useAnnotations = useAnnotations
        
        # important variables and containers
        self.db = None
        self.hom = None
        self.invHom = None
        self.groupingObject = None
        self.cvObjects = []
        self.features = []
        self.imgObjects = []
        self.lanes = None
        
        # key/mouse bindings
        self.addKeyBindings(['J','Shift + J'], 'joinSelected')                                      # J / Shift + J - join selected objects
        self.addKeyBindings(['X','Shift + X'], 'explodeObject')                                     # X / Shift + X - explode selected object
        self.addKeyBindings(['K','Shift + K'], 'deleteObject')                                      # K / Shift + K - delete selected objects
        self.addKeyBindings(['Ctrl + T'], 'saveObjects', warnDuplicate=False)                       # Ctrl + T - save annotated objects to table
        self.addKeyBindings(['Ctrl + O'], 'toggleObjectFeaturePlotting')                            # Ctrl + O - toggle object feature plotting
        self.addKeyBindings(['M'], 'toggleHideMovingObjects')                                       # M - toggle moving object plotting
        self.addKeyBindings(['Ctrl + M'], 'hideAllMovingObjects')                                   # Ctrl + M - turn off object plotting
        self.addKeyBindings(['Ctrl + Shift + M'], 'unhideAllMovingObjects')                         # Ctrl + Shift + M - turn on object plotting
        self.addKeyBindings(['Ctrl + L'], 'checkLane')                                              # Ctrl + L - check the lane of a selected object (or all objects on screen)
        if self.enableDrawAllFeatures:
            # only add this capability if it was enabled, to avoid confusing the user
            self.addKeyBindings(['Ctrl + Shift + O'], 'toggleAllFeaturePlotting')                   # Ctrl + Shift + O - toggle feature plotting
    
    def open(self):
        """Open the video and database."""
        # open the database first (which also loads the homography and creates the image objects)
        # it will start loading trajectories in a separate process and return them as they are finished
        self.openDatabase()
        
        # open a window (which also sets up to read keys and mouse clicks)
        self.openGUI()
        
        # load lanes into a LaneCollection
        self.lanes = cvgeom.LaneCollection(self.objects)
        print("Loaded {} lanes from config !".format(self.lanes.nLanes))
        
        # open the video (which also sets up the trackbar)
        self.openVideo()
    
    # ### Methods for interacting with the database ###
    def openDatabase(self):
        """Open the database with the trajstorage.CVsqlite class, load in the objects,
           load the homography, and create an ImageObject for each object for working
           in image space."""
        if self.databaseFilename is not None and self.homographyFilename is not None:
            # read the homography if we have one
            print "Loading homography from file '{}'".format(self.homographyFilename)
            self.hom = np.loadtxt(self.homographyFilename)
            self.invHom = cvhomog.Homography.invertHomography(self.hom)
            print "Starting reader for on database '{}'".format(self.databaseFilename)
            self.db = trajstorage.CVsqlite(self.databaseFilename, objTablePrefix=self.objTablePrefix, withFeatures=self.withFeatures, homography=self.hom, invHom=self.invHom, withImageBoxes=self.withBoxes, allFeatures=self.enableDrawAllFeatures)
            
            if self.useAnnotations:
                # if using annotations, get the latest annotations table
                if self.db.getLatestAnnotation():
                    self.objTablePrefix = self.db.latestannotations.replace('objects_features', '')
                    print("Reading object groups from annotations table with prefix {} ...".format(self.objTablePrefix))
                    self.db = trajstorage.CVsqlite(self.databaseFilename, objTablePrefix=self.objTablePrefix, withFeatures=self.withFeatures, homography=self.hom, invHom=self.invHom, withImageBoxes=self.withBoxes, allFeatures=self.enableDrawAllFeatures)
                else:
                    print("No annotations available. Defaulting to original objects...")
            
            self.db.loadObjectsInThread()
            self.cvObjects, self.features = self.db.objects, self.db.features
            self.imgObjects = self.db.imageObjects
            print "Objects are now loading from the database in a separate thread"
            print "You may notice a slight delay in loading the objects after the video first starts."
    
    def cleanup(self):
        if self.db is not None:
            self.db.close()
    
    def saveObjects(self, key=None):
        """Save all of the objects to new tables (with the given tablePrefix) in the database."""
        self.saveObjectsToTable()

    def saveObjectsToTable(self, tablePrefix=None):
        """Save all of the objects to new tables (with the given tablePrefix) in the database."""
        tablePrefix = time.strftime("annotations_%d%b%Y_%H%M%S_") if tablePrefix is None else tablePrefix
        objList = []
        for o in self.imgObjects:
            olist = o.getObjList()
            #if None in olist:
                #print o
                #print(olist)
            objList.extend(olist)
        print "Saving {} objects with table prefix {} ...".format(len(objList), tablePrefix)
        self.db.writeObjects(objList, tablePrefix)
        
    # ### Methods for rendering/playing annotated video frames ###
    def toggleAllFeaturePlotting(self):
        """Toggle plotting of ALL features on/off by changing the drawAllFeatures flag."""
        self.drawAllFeatures = not self.drawAllFeatures
        ofonn = 'on' if self.drawAllFeatures else 'off'
        print "ALL feature plotting {}".format(ofonn)
        self.update()
    
    def toggleObjectFeaturePlotting(self):
        """Toggle object feature plotting on/off by changing the drawObjectFeatures flag."""
        self.drawObjectFeatures = not self.drawObjectFeatures
        ofonn = 'on' if self.drawObjectFeatures else 'off'
        print "Object feature plotting {}".format(ofonn)
        self.update()
    
    def toggleHideMovingObjects(self):
        """Toggle moving object plotting on/off without affecting other cvgeom objects."""
        self.toggleHideObjList(self.movingObjects)
        self.update()
    
    def hideAllMovingObjects(self):
        """Turn off moving object plotting without affecting other cvgeom objects."""
        self.hideAllInObjList(self.movingObjects)
        self.update()
    
    def unhideAllMovingObjects(self):
        """Turn on moving object plotting without affecting other cvgeom objects."""
        self.unhideAllInObjList(self.movingObjects)
        self.update()
    
    def plotFeaturePoint(self, feat, i, color='random'):
        """Plot the features that make up the object as points (with no historical trajectory)."""
        if feat.existsAtInstant(i):
            if not hasattr(feat, 'color'):
                feat.color = cvgui.getColorCode(color)
            fp = cvmoving.getFeaturePositionAtInstant(feat, i, invHom=self.invHom)
            p = cvgeom.imagepoint(fp.x, fp.y, color=feat.color)
            self.drawPoint(p, pointIndex=False)
        
    def plotObjectFeatures(self, obj, i):
        """Plot the features that make up the object as points (with no historical trajectory)."""
        if len(obj.subObjects) > 0:
            for o in obj.subObjects:
                self.plotObjectFeatures(o, i)           # recurse into sub objects
        else:
            if obj.existsAtInstant(i) and obj.drawAsJoined():
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
        if obj.isExploded:
            # plot features and sub objects
            for f in obj.ungroupedFeatures.values():
                self.plotFeaturePoint(f, endPos, color=obj.color)
            if len(obj.subObjects) > 0:
                # if this object has sub objects, plot those instead (recursing)
                for o in obj.subObjects:
                    self.plotObject(o, endPos)
        else:
            # otherwise plot this object
            if obj.existsAtInstant(endPos):
                if obj.drawAsJoined() and not obj.hidden:
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
                            cv2.line(self.img, a, b, obj.color)
                        
                        # plot the object position as a point
                        p = cvgeom.imagepoint(p.x,p.y,color=obj.color)
                        self.drawPoint(p, pointIndex=False)
                        
                        # also the features
                        if self.drawObjectFeatures:
                            self.plotObjectFeatures(obj, endPos)
            #elif obj.getNum() in self.objects and isinstance(self.objects[obj.getNum()], cvgeom.imagebox):
                ## if this object doesn't exist but is still drawn, remove it from the list
                #del self.objects[obj.getNum()]
    
    def dbUpdate(self):
        self.db.update()
        for mo in self.imgObjects:
            if mo.obj.num not in self.movingObjects:
                self.movingObjects[mo.obj.num] = cvgeom.PlaneObjectTrajectory.fromImageObject(mo)
    
    def drawExtra(self):
        # update objects from database reader
        self.dbUpdate()
        #self.objects = cvgeom.ObjectCollection()
        #self.points = cvgeom.ObjectCollection()
        if self.drawAllFeatures:
            self.drawFeaturePoints()
        if self.drawObjectFeatures or (not self.drawObjectFeatures and not self.drawAllFeatures):
            self.drawTrajObjects()
    
    def drawFeaturePoints(self):
        """Add all features in the current frame to the image."""
        i = self.getVideoPosFrames()               # get the current frame number
        if i < self.nFrames - 1:
            for feat in self.features:
                self.plotFeaturePoint(feat, i)
    
    def drawTrajObjects(self):
        """Add annotations to the image, and show it in the player."""
        # go through each object to draw them on the image
        i = self.getVideoPosFrames()               # get the current frame number
        if i < self.nFrames - 1:
            for obj in self.imgObjects:
                self.plotObject(obj, i)
    
    # ### Methods for joining/exploding objects (using actions so they can be undone/redone) ###
    def finishCreatingObject(self):
        if self.creatingObject is not None:
            if self.groupingObject is not None:
                self.joinFeaturesInRegion(self.creatingObject)
                self.createRegion()
            else:
                super(cvTrajOverlayPlayer, self).finishCreatingObject()
    
    def escapeCancel(self, key=None):
        """Stop the feature grouper."""
        super(cvTrajOverlayPlayer, self).escapeCancel(key=key)
        if self.groupingObject is not None:
            self.groupingObject = None
            self.isPaused = False
    
    def joinFeaturesInRegion(self, reg):
        poly = reg.polygon()
        feats = []
        # get all the features inside the region
        for f in self.groupingObject.ungroupedFeatures.values():
            i = self.getVideoPosFrames()
            if f.existsAtInstant(i):
                fp = cvmoving.getFeaturePositionAtInstant(f, i, invHom=self.invHom)
                if poly.contains(fp.asShapely()):
                    feats.append(f.num)
        
        # group the features
        a = FeatureGrouper(self.groupingObject, feats, self.hom, self.invHom, self.movingObjects)
        self.do(a)
    
    def joinSelected(self, key=None):
        """Join the selected objects."""
        # create an ObjectJoiner object with the current list of selected objects
        sobjs = self.selectedFromObjList('movingObjects')
        objs = []
        mobjs = []
        for i in sobjs.keys():
            if i < len(self.imgObjects):
                objs.append(self.imgObjects[i])
                mobjs.append(sobjs[i])
        #print self.imgObjects
        a = ObjectJoiner(objs, mobjs)
        
        # call our do() method (inherited from cvGUI) with the action so it can be undone
        self.do(a)
        
        # added clearSelected() to deselect after joining selected boxes
        self.clearSelected()
        
        # update the list of objects to draw to reflect only the object that represents the joined objects
        #oids = sorted(sobjs.keys())
        #for oid in oids[1:]:
            #if oid in self.objects:
                #del self.objects[oid]
        #self.selectedObjects = [o for o in self.selectedObjects if o.drawAsJoined(self.getVideoPosFrames())]
    
    def explodeObject(self, key=None):
        """
        Explode the selected object(s) into their features, allowing their grouping
        to be edited.
        """
        # ImageObject(MovingObject.fromFeatures(oId, feats), self.hom, self.invHom)
        
        # create an ObjectExploder object with the current list of selected objects
        sobjs = self.selectedFromObjList('movingObjects')
        if len(sobjs) >= 1:
            self.isPaused = True
            i = sobjs.keys()[0]
            if len(sobjs) > 1:
                print "You can only explode one object at a time!"
            print "Exploding object {} ...".format(i)
            if i < len(self.imgObjects):
                io = self.imgObjects[i]
                mo = sobjs[i]
                a = ObjectExploder([io], [mo])
                self.do(a)
                self.groupingObject = io
                self.createRegion()
        
    def deleteObject(self, key=None):
        """Delete the selected objects."""
        # create an ObjectDeleter object with the current list of selected objects
        sobjs = self.selectedFromObjList('movingObjects')
        objs = []
        mobjs = []
        for i in sobjs.keys():
            if i < len(self.imgObjects):
                objs.append(self.imgObjects[i])
                mobjs.append(sobjs[i])
        #print self.imgObjects
        a = ObjectDeleter(objs, mobjs)
        
        # call our do() method (inherited from cvGUI) with the action so it can be undone
        self.do(a)
        
        # added clearSelected() to deselect after joining selected boxes
        self.clearSelected()
    
    # ### Methods for testing objects ###
    def checkLane(self, key=None):
        """
        Use the lanes loaded from config to assign a lane to object(s) in the 
        current frame. Works on the selected object, or all objects at the
        current frame if none are selected.
        """
        # first make sure we have lanes in the first place
        if self.lanes is not None and self.lanes.nLanes > 0:
            # get objects
            sobjs = self.selectedFromObjList('movingObjects')
            if len(sobjs) > 0:
                # selected objects
                objs = [self.imgObjects[i] for i in sobjs.keys() if i < len(self.imgObjects)]
            else:
                # no selected objects - take all objects at current instant
                objs = [o for o in self.imgObjects if o.existsAtInstant(self.posFrames)]
            
            # loop through objects and assign lanes
            hs = "At frame {}:".format(self.posFrames)
            print('\n' + hs)
            print('-'*len(hs))
            for o in objs:
                print("Object {}: lane {}".format(o.getNum(), self.lanes.assignLaneAtInstant(o, self.posFrames)))
        else:
            print("No lanes defined in config!")