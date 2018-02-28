#!/usr/bin/python
"""A script for running a cvTrajOverlay player with a video, and optionally adding overlay from database of trajectory data.."""

# TODO rewrite this to use 2 windows in the same process so we don't have to do so much IPC trickery

import os, sys, time, argparse, traceback
from configobj import ConfigObj
import rlcompleter, readline
from copy import deepcopy
import numpy as np
import threading
import multiprocessing, Queue
import cvgui, cvgeom, cvhomog
import cv2

class ProjObjectAdder(cvgui.ObjectAdder):
    """Alternate point adder to reflect changes in projected viewer."""
    def __init__(self, objects, o, projQueue=None):
        super(ProjObjectAdder, self).__init__(objects, o)
        self.projQueue = projQueue
    
    def undo(self):
        # call the ObjectAdder undo then put a None point in the queue
        super(ProjObjectAdder, self).undo()
        for o in self.objList:
            self.projQueue.put(cvgeom.imagepoint(index=o.getIndex()))

class ProjObjectDeleter(cvgui.ObjectDeleter):
    """Alternate point deleter to reflect changes in projected viewer."""
    def __init__(self, objects, dList, projQueue=None):
        super(ProjObjectDeleter, self).__init__(objects, dList)
        self.projQueue = projQueue
    
    def do(self):
        # call the ObjectDeleter do then put a None point in the queue
        super(ProjObjectDeleter, self).do()
        for dList in self.dList:
            for i in dList.keys():
                self.projQueue.put(cvgeom.imagepoint(index=i))
    
class ObjectTransferer(cvgui.action):
    """A class for tranfering an object from one collection to another."""
    def __init__(self, fromList, toList, o, newIndex=None, newColor=None):
        self.fromList = fromList
        self.toList = toList
        self.o = o
        self.newIndex = newIndex
        self.newColor = newColor
        self.name = str(o)
        
        # make a copy of the object for inserting
        self.newObj = deepcopy(self.o)
        if self.newIndex is not None:
            self.newObj.setIndex(self.newIndex)
        if self.newColor is not None:
            self.newObj.setColor(self.newColor)
        
        # create an ObjectAdder to handle the insert
        self.objAdder = cvgui.ObjectAdder(self.toList, self.newObj)
        
        # and an ObjectDeleter to handle the deletion (with the original object)
        self.objDeleter = cvgui.ObjectDeleter(self.fromList, {self.o.getIndex(): self.o})
        
    def do(self):
        """Remove the object from fromList and insert it into toList."""
        # call the adder and deleter's do methods
        self.objAdder.do()
        self.objDeleter.do()
    
    def undo(self):
        """Remove the object from toList and insert it back into fromList."""
        # call the adder and deleter's undo methods
        self.objDeleter.undo()
        self.objAdder.undo()
    
class HomogInput(cvgui.cvGUI):
    """A cvGUI class for working with homographies, adding the capability to add
       projected points to the image."""
    def __init__(self, imageFilename, configFilename=None, isCameraFrame=False, **kwargs):
        # flags to override
        overrideFlags = ['saveFrameFlag', 'testProjection']
        newFlags = {k: kwargs.pop(k) for k in kwargs.keys() if k in overrideFlags}
        
        # construct cvGUI object
        super(HomogInput, self).__init__(imageFilename, configFilename=None, **kwargs)
        
        # homography-specific properties
        self.isCameraFrame = isCameraFrame
        
        self.pointQueue = multiprocessing.Queue()
        self.projectedPointQueue = multiprocessing.Queue()
        self.testPointQueue = multiprocessing.Queue()
        self.projectedPoints = cvgeom.ObjectCollection()                                     # collection of points projected from the other image (visible, but can't be manipulated)
        self.recalculate = multiprocessing.Value('b', False)                                 # flag for GUI to call for recalculating homography
        self.savetxt = multiprocessing.Value('b', False)                                     # flag for GUI to call for savetxt homography
        self.savePts = multiprocessing.Value('b', False)                                     # flag for GUI to call for saving all info (reuses Ctrl + S as shortcut)
        self.saveHomog = multiprocessing.Value('b', False)                                   # flag for GUI to call for saving the homography to the history
        self.saveFrameFlag = multiprocessing.Value('b', False)                               # flag for GUI to call for saving frame to image file
        self.quitApp = multiprocessing.Value('b', False)                                     # flag for GUI to call for quitting the entire application
        self.homographies = {}                                                               # a list of all the homographies we have calculated
        self.error = multiprocessing.Value('f', -1)                                          # error in world units (-1 if not set)
        self.testProjection = multiprocessing.Value('b', False)                              # flag for GUI to call for testing projection of points
        self.testPoint = multiprocessing.Array('f', 2)                                       # point to use for test projection
        
        # override approved flags so they can be shared between two processes
        for k, v in newFlags.iteritems():
            if hasattr(self, k):
                setattr(self, k, v)
        
        # extra keybindings                                                                  
        self.addKeyBindings(['Ctrl + R'], 'setRecalculateFlag')                              # Ctrl + r - recalculate homography & refresh
        self.addKeyBindings(['Ctrl + Shift + H'], 'setSaveTxt', warnDuplicate=False)         # Ctrl + Shift + H - save homography with numpy savetxt
        self.addKeyBindings(['Ctrl + Shift + F'], 'setSaveFrame', warnDuplicate=False)       # Ctrl + Shift + F - save frames to image files
        self.addKeyBindings(['Ctrl + Shift + A'], 'quickOutput')                             # Ctrl + Shift + F - save frames to image files
        self.addKeyBindings(['Ctrl + H'], 'setSaveHomog', warnDuplicate=False)               # Ctrl + H - save homography in dict
        self.addKeyBindings(['Ctrl + Shift + Q'], 'setQuitApp')                              # Ctrl + Shift + q - quit application
        self.addKeyBindings(['Ctrl + Shift + P'], 'toggleTestProjection')                    # Ctrl + Shift + P - toggle test projection on/off
        
    def setError(self, error):
        """Set the error value so it is displayed in the upper-left corner of the image."""
        self.error.value = error
    
    def getError(self):
        if self.haveError():
            return self.error.value
    
    def clearError(self):
        """Set the error value to -1 so it is NOT displayed in the upper-left corner of the image."""
        self.error.value = -1
        
    def haveError(self):
        return self.error.value != -1
    
    def quickOutput(self):
        """
        Recalculate the homography, refresh the images, save points to config, save homography
        matrix to file with numpy.savetxt, and save the two images with annotations to PNG files.
        """
        # NOTE/TODO using sleeps as quick and dirty way to achieve synchronization between processes, since this whole tool will be rewritten soon
        self.setRecalculateFlag()
        time.sleep(0.1)
        self.setSaveHomog()
        time.sleep(0.1)
        self.saveConfig()
        time.sleep(0.1)
        self.setSaveTxt()
        time.sleep(0.1)
        self.setSaveFrame()
    
    def toggleTestProjection(self):
        """Toggle on/off testing projection of points between the two images."""
        print "Turning projection testing {} ...".format('off' if self.testProjection.value else 'on')
        self.testProjection.value = not self.testProjection.value
    
    def setRecalculateFlag(self):
        """Recalculate the homography and reproject the points."""
        self.recalculate.value = True
        
    def recalculateDone(self):
        self.recalculate.value = False
       
    def needRecalculate(self):
        return self.recalculate.value
    
    def setSaveTxt(self):
        """Save the homography with numpy.savetxt (for using with TrafficIntelligence)."""
        self.savetxt.value = True
        
    def saveTxtDone(self):
        self.savetxt.value = False
       
    def needSaveTxt(self):
        return self.savetxt.value
    
    def setSaveHomog(self):
        """Save the homography to the history (for future implementation plans)."""
        self.saveHomog.value = True
    
    def setSaveFrame(self):
        """Save the two frames as they currently appear to image files."""
        self.saveFrameFlag.value = True
        
    def saveFrameDone(self):
        self.saveFrameFlag.value = False
       
    def needSaveFrame(self):
        return self.saveFrameFlag.value
    
    def setSaveHomog(self):
        """Save the homography to the history (for future implementation plans)."""
        self.saveHomog.value = True
    
    def saveHomogDone(self):
        self.saveHomog.value = False
    
    def needSaveHomog(self):
        return self.saveHomog.value
    
    def saveConfig(self):
        """Save all of the information we have into the configuration file."""
        self.savePoints()
    
    def savePoints(self):
        """Set the flag to save points."""
        self.savePts.value = True
        
    def savePointsDone(self):
        self.savePts.value = False
    
    def needSavePoints(self):
        return self.savePts.value
    
    def setQuitApp(self):
        """
        Close BOTH windows and quit the application (may not work if one window
        has already been closed)
        """
        self.quitApp.value = True
        
    def needQuitApp(self):
        return self.quitApp.value
    
    def userCheckXY(self, x, y):
        """
        Project the point to the other image using the homography we have and
        print the coordinates to the terminal. If projecting from the aerial
        image, the result will be in image coordinates. If projecting from the
        camera frame, the result will be in world coordinates (i.e. units as
        determined by the unitsPerPixel value provided).
        """
        if self.testProjection.value:
            p = cvgeom.fimagepoint(x, y)
            self.testPointQueue.put(p)
    
    def addPoint(self, x, y):
        i = self.points.getNextIndex()
        p = cvgeom.imagepoint(x, y, index=i, color='blue')
        a = ProjObjectAdder(self.points, p, self.pointQueue)
        self.do(a)
        
    def deleteSelected(self):
        """Delete the points from the list, in a way that can be undone."""
        selp = self.selectedPoints()
        a = ProjObjectDeleter(self.points, selp, self.pointQueue)
        selo = self.selectedObjects()
        a.addObjects(self.objects, selo)
        self.do(a)
        
    def getProjectedPoints(self):
        """Get any points in the projected point queue and update our list of projected points."""
        while not self.projectedPointQueue.empty():
            try:
                p = self.projectedPointQueue.get(False)
                if p.isNone():
                    # if we get a None imagepoint, we should remove it from our list of projected points
                    if p.getIndex() in self.projectedPoints:
                        self.projectedPoints.pop(p.getIndex())
                        self.update()
                else:
                    # otherwise put it in the dict for plotting in red
                    p.setColor('red')
                    self.projectedPoints[p.index] = p
            except Queue.Empty:
                break
        
    def putPoints(self):
        """Add all points to the point queue so they can be received by the other process."""
        if self.isAlive():
            for p in self.points.values():
                self.pointQueue.put(p)
        
    def drawFrame(self):
        # clear the image
        self.clear()
        
        # call cvGUI's drawFrame to draw the objects owned by this instance
        super(HomogInput, self).drawFrame()
        
        # put our points in the queue
        self.putPoints()
        
        # add the projectedPoints
        self.getProjectedPoints()
        for i, p in self.projectedPoints.iteritems():
            self.drawPoint(p)
        
        if self.needSaveFrame():
            self.saveFrameImage()
            time.sleep(0.1)                 # NOTE/TODO hack to "synchronize" the threads - not doing anything more permanent since this whole tool will be rewritten in the near future
            self.saveFrameDone()
        
        # add the error if we have it
        if self.haveError():
            eStr = "Error = {} world units squared".format(round(self.getError(), 3))
            self.drawText(eStr, 11, 31, fontSize=2)
    
class HomogInputVideo(cvgui.cvPlayer):
    """A class for collecting user input from a video file to augment a homography
       so that it accounts for the height of objects in a particular plane in the
       image. This is intended for use when extracting pedestrian data."""
       
    # TODO need to be able to save these points (that's why they are MultiPointObjects)
       
    def __init__(self, videoFilename, groundHomogFilename, augHomogFilename=None, **kwargs):
        super(HomogInputVideo, self).__init__(videoFilename, **kwargs)
        
        # properties specific to this process
        self.groundHomogFilename = groundHomogFilename
        self.augHomogFilename = augHomogFilename
        self.worldPoints = None
        self.cameraPoints = None
        if self.augHomogFilename is None:       # generate the new filename if we didn't get one
            fname, fext = os.path.splitext(self.groundHomogFilename)
            self.augHomogFilename = fname + '_augmented' + fext
        
        self.groundHomog = cvhomog.Homography(homographyFilename=self.groundHomogFilename)
        self.augHomog = None
        if self.groundHomog.homography is None:
            return          # exit if problem opening homography
        self.groundPoints = cvgeom.MultiPointObject(index='', name='groundPoints', color='green')
        self.airPoints = cvgeom.MultiPointObject(index='', name='airPoints', color='cyan')
        
        self.addKeyBindings(['Z'], 'addGroundPoint')                                            # Z - add 'ground' point - a point on the ground in the plane of interest
        self.addKeyBindings(['A'], 'addAirPoint')                                               # A - add 'air' point - a point assumed to be directly above the last ground point added
        self.addKeyBindings(['Ctrl + Shift + H'], 'computeHomography', warnDuplicate=False)     # Ctrl + Shift + H - compute augmented homography and save it with savetxt
    
    def addGroundPoint(self, key=None):
        """Add the selected point to the list of ground points."""
        pts = self.selectedPoints()
        if len(pts) > 0:
            p = pts.values()[0]         # only take one point
            p.deselect()
            
            # create a transfer action to move the point to the ground list with the next available index
            newIndex = self.groundPoints.getNextIndex()
            a = ObjectTransferer(self.points, self.groundPoints.points, p, newIndex=newIndex, newColor='green')
            self.do(a)
    
    def addAirPoint(self, key=None):
        pts = self.selectedPoints()
        if len(pts) > 0:
            p = pts.values()[0]
            p.deselect()
            
            # create a transfer action to move the point to the air point list with the last ground point index we used
            newIndex = self.airPoints.getNextIndex()
            a = ObjectTransferer(self.points, self.airPoints.points, p, newIndex=newIndex, newColor='cyan')
            self.do(a)
    
    def computeHomography(self, key=None):
        """Compute the augmented homography and save it to augHomogFilename with np.savetxt."""
        # go through the ground/air point pairs to create world points and camera points
        self.worldPoints = cvgeom.ObjectCollection()
        self.cameraPoints = cvgeom.ObjectCollection()
        if len(self.groundPoints.points) == len(self.airPoints.points) and len(self.groundPoints.points) >= 4:
            print "Building points..."
            for i in sorted(self.groundPoints.points.keys()):
                # get the points if we can
                if i in self.groundPoints.points and i in self.airPoints.points:
                    gp = self.groundPoints.points[i]
                    ap = self.airPoints.points[i]
                    
                    # calculate the location of the ground point in world space
                    wx, wy = self.groundHomog.projectToWorld(gp, objCol=False)
                    gi = self.worldPoints.getNextIndex()
                    wpg = cvgeom.fimagepoint(wx, wy, index=gi)
                    
                    # record the camera ground point and world ground point
                    self.cameraPoints[gi] = gp
                    self.worldPoints[gi] = wpg
                    
                    # get the next index from the world points and remake the world point
                    ai = self.worldPoints.getNextIndex()
                    wpa = cvgeom.fimagepoint(wx, wy, index=ai)
                    
                    # now record the air point assuming that it corresponds to the ground point
                    self.cameraPoints[ai] = ap
                    self.worldPoints[ai] = wpa
            
            # compute the augmented homography if we got enough points
            if len(self.worldPoints) == len(self.cameraPoints) and len(self.worldPoints) >= 4:
                print "Computing augmented homography..."
                self.augHomog = cvhomog.Homography(cameraPoints=self.cameraPoints, worldPoints=self.worldPoints)
                self.augHomog.findHomography()
                
                print "Saving augmented homography to file '{}' ...".format(self.augHomogFilename)
                self.augHomog.savetxt(self.augHomogFilename)
                print "Done!"
            else:
                print "Something weird happened when building the points..."
        else:
            print "Need at least 4 ground points to calculate the homography!"
    
    def drawExtra(self):
        """Draw the ground points and air points on the video frame."""
        self.drawObject(self.groundPoints)
        self.drawObject(self.airPoints)
    
def fillPointQueue(qTo, a):
    for p in a.values():
        qTo.put(p)

def drainPointQueue(qFrom):
    a = {}
    while not qFrom.empty():
        try:
            p = qFrom.get(False)
            a[p.getIndex()] = p
        except Queue.Empty:
            break
    return a

def holdNones(points):
    nones = []
    for i in points.keys():
        if points[i].isNone():
            nones.append(points.pop(i))
    return nones

def returnNones(points, nones):
    for p in nones:
        if p.getIndex() not in points:
            points[p.getIndex()] = p

def saveConfig(cfgObj, name, aerialImageFile, cameraImageFile, unitsPerPixel, aerialPoints, cameraPoints, homographies):
    """Save all of the information we have, including the names of the two image
       files, the unitsPerPixel, both sets of points, and all of the homographies
       we have calculated."""
    # first create (or clear) the old section
    cfgObj[name] = {}
    # then get the section with this name
    cfg = cfgObj[name]
    
    # add the global fields
    cfg['aerialImage'] = aerialImageFile
    cfg['cameraImage'] = cameraImageFile
    cfg['unitsPerPixel'] = unitsPerPixel
    
    # add the points in their own section
    cfg['points'] = {}
    cfg['points']['aerialPoints'] = {}
    for i, p in aerialPoints.iteritems():
        cfg['points']['aerialPoints'][str(i)] = (p.x, p.y)
    
    cfg['points']['cameraPoints'] = {}
    for i, p in cameraPoints.iteritems():
        cfg['points']['cameraPoints'][str(i)] = (p.x, p.y)
        
    # then add the homographies to another section
    cfg['homographies'] = {}
    for d, hom in homographies.iteritems():
        cfg['homographies'][d] = hom.toString()

def loadConfig(cfgObj, name):
    aerialImageFile, cameraImageFile, unitsPerPixel, aerialPoints, cameraPoints, homographies = None, None, None, None, None, None
    if name in cfgObj:
        cfg = cfgObj[name]
        if 'aerialImage' in cfg:
            aerialImageFile = cfg['aerialImage']
        if 'cameraImage' in cfg:
            cameraImageFile = cfg['cameraImage']
        if 'unitsPerPixel' in cfg:
            unitsPerPixel = float(cfg['unitsPerPixel'])
        if 'points' in cfg:
            if 'aerialPoints' in cfg['points']:
                aerialPoints = cvgeom.ObjectCollection()
                for i, p in cfg['points']['aerialPoints'].iteritems():
                    aerialPoints[int(i)] = cvgeom.imagepoint(int(p[0]), int(p[1]), index=int(i), color='blue')
            if 'cameraPoints' in cfg['points']:
                cameraPoints = cvgeom.ObjectCollection()
                for i, p in cfg['points']['cameraPoints'].iteritems():
                    cameraPoints[int(i)] = cvgeom.imagepoint(int(p[0]), int(p[1]), index=int(i), color='blue')
        if 'homographies' in cfg:
            homographies = {}
            for d, hom in cfg['homographies'].iteritems():
                homographies[d] = cvhomog.Homography.fromString(hom, aerialPoints=aerialPoints, cameraPoints=cameraPoints, unitsPerPixel=unitsPerPixel)
    else:
        print "ConfigObj section {} not found!".format(name)
    return aerialImageFile, cameraImageFile, unitsPerPixel, aerialPoints, cameraPoints, homographies

# Entry point
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Program for creating and editing homographies from aerial and camera images and user input. Also capable of augmenting homographies using user input taken while playing a video file (if a video file is provided with the -v option).")
    parser.add_argument('-w', dest='aerialImageFile', help="File containing the aerial image.")
    parser.add_argument('-i', dest='cameraImageFile', help="File containing a sample camera frame.")
    parser.add_argument('-v', dest='videoFilename', help="File containing a video that should be used to augment the homography. This requires that you provide a homography that has already been computed, which will be used when performing the adjustment.")
    parser.add_argument('-u', dest='unitsPerPixel', type=float, help="Units of the aerial image in units/pixel. Should be below 1 (e.g. 0.5 ft/pixel).")
    parser.add_argument('-f', dest='configFilename', default='homMaker_points.txt', help="Name of file containing saved data.")
    parser.add_argument('-s', dest='configSection', help="Name of section of file where data is saved")
    parser.add_argument('-o', dest='homographyFilename', default='homography.txt', help="Name of file for outputting the final homography (with numpy.savetxt, readable by TrafficIntelligence).")
    parser.add_argument('-a', dest='augHomogFilename', help="Name of file for outputting the augmented homography (with numpy.savetxt, so also readable by TrafficIntelligence). If not provided, the name is generated from the name of the input homography. Note that this option only applies to video selection (i.e. the -v option with a video filename).")
    parser.add_argument('-pk', dest='printKeys', action='store_true', help="Print keys that are read from the video window (useful for adding shortcuts and other functionality).")
    parser.add_argument('-pm', dest='printMouseEvents', type=int, nargs='*', help="Print mouse events that are read from the video window (useful for adding other functionality). Optionally can provide a number, which signifies the minimum event flag that will be printed.")
    parser.add_argument('-r', dest='clickRadius', type=int, default=10, help="Radius of clicks on the image (in pixels) (default: %(default)s).")
    parser.add_argument('-fs', dest='textFontSize', type=float, default=4.0, help="Size of the font used for image annotations (in points) (default: %(default)s).")
    #parser.add_argument('-i', dest='interactive', action='store_true', help="Show the image in a separate thread and start an interactive shell.")
    args = parser.parse_args()
    configFilename = args.configFilename
    configSection = "A-{}_C-{}".format(args.aerialImageFile, args.cameraImageFile) if args.configSection is None else args.configSection
    homographyFilename = args.homographyFilename
    augHomogFilename = args.augHomogFilename
    videoFilename = args.videoFilename
    interactive = True
    hom = None
    ret = 0
    
    if videoFilename is not None:
        # make sure we got a homography and it exists
        if homographyFilename is None:
            print "Error: You must provide a homography when augmenting with a video! Exiting..."
            sys.exit(2)
        elif not os.path.exists(homographyFilename):
            print "Error: The homography file '{}' does not exist. Exiting...".format(homographyFilename)
            sys.exit(4)
        
        # use the video input class to collect ground/air point pairs
        videoInput = HomogInputVideo(videoFilename, homographyFilename, augHomogFilename=augHomogFilename, configFilename=configFilename, configSection=configSection, clickRadius=args.clickRadius, textFontSize=args.textFontSize)
        videoInput.run()
    else:
        if args.unitsPerPixel is None:
            print "Error: you must specify the scale (unitsPerPixel, the -u argument) of the aerial image! Exiting..."
            sys.exit(1)
        
        # otherwise use the standard dual image homography creator
        # create a configobj so we can load/save info
        cfgObj = ConfigObj(configFilename)
        
        aerialImageFile, cameraImageFile, unitsPerPixel, aerialPoints, cameraPoints, homographies = loadConfig(cfgObj, configSection)
        
        # override the file names and units per pixel read in the config if provided in the command
        aerialImageFile = args.aerialImageFile if args.aerialImageFile is not None else aerialImageFile
        cameraImageFile = args.cameraImageFile if args.cameraImageFile is not None else cameraImageFile
        unitsPerPixel = args.unitsPerPixel if unitsPerPixel is None else unitsPerPixel
        
        # create the cvGUI objects
        aerialInput = HomogInput(aerialImageFile, configFilename=configFilename, printKeys=args.printKeys, printMouseEvents=args.printMouseEvents, clickRadius=args.clickRadius, textFontSize=args.textFontSize, autosaveInterval=60)
        cameraInput = HomogInput(cameraImageFile, saveFrameFlag=aerialInput.saveFrameFlag, testProjection=aerialInput.testProjection, isCameraFrame=True, configFilename=configFilename, printKeys=args.printKeys, printMouseEvents=args.printMouseEvents, clickRadius=args.clickRadius, textFontSize=args.textFontSize, autosaveInterval=60)
        
        # get the signals (multiprocessing.Value objects to communicate between processes)
        aSig = aerialInput.getAliveSignal()
        cSig = cameraInput.getAliveSignal()
        
        # set the points in the HomogInputs if we read some from the config
        if isinstance(aerialPoints, cvgeom.ObjectCollection):
            aerialInput.points = aerialPoints
        if isinstance(cameraPoints, cvgeom.ObjectCollection):
            cameraInput.points = cameraPoints
        
        # set the homographies or create a new dict
        homographies = {} if homographies is None else homographies
        
        # show the windows
        aerialInput.runInThread()
        time.sleep(2)
        cameraInput.runInThread()
        
        try:
            aerialPoints = cvgeom.ObjectCollection()
            cameraPoints = cvgeom.ObjectCollection()
            while aSig.value or aerialInput.needSavePoints() or cSig.value or cameraInput.needSavePoints():
                # update the two collections of points
                aPoints = drainPointQueue(aerialInput.pointQueue)
                for i, p in aPoints.iteritems():
                    aerialPoints[i] = p
                cPoints = drainPointQueue(cameraInput.pointQueue)
                for i, p in cPoints.iteritems():
                    cameraPoints[i] = p
                #print "a: {}   c: {}".format(len(aerialPoints), len(cameraPoints))
                
                # if we need to calculate the homography, do that
                if hom is None or aerialInput.needRecalculate() or cameraInput.needRecalculate():
                    if len(aerialPoints) >= 4 and len(cameraPoints) >= 4:
                        if len(aerialPoints) == len(cameraPoints):
                            print "Calculating homography with {} point pairs...".format(len(aerialPoints))
                            hom = cvhomog.Homography(aerialPoints, cameraPoints, unitsPerPixel)
                            try:
                                hom.findHomography()
                            except:
                                print traceback.format_exc()
                                print "There was an error calculating the homography. See above for details. You probably need to change some points."
                            #error = hom.calculateError(squared=True)
                            # TODO error calculation should really use DIFFERENT points to really give a meaningful value
                            #   - how about a key for moving points between the homography-computation set and the error-calculation set?
                            #print "Error = {} world units".format(round(error,3))
                            #aerialInput.setError(error)
                    aerialInput.recalculateDone()
                    cameraInput.recalculateDone()
                    
                if hom is not None:
                    # if we have points, project them
                    if len(aerialPoints) > 0:
                        nones = holdNones(aerialPoints)
                        projAerialPts = hom.projectToImage(aerialPoints, fromAerial=True)
                        returnNones(projAerialPts, nones)
                        fillPointQueue(cameraInput.projectedPointQueue, projAerialPts)
                        
                    if len(cameraPoints) > 0:
                        nones = holdNones(cameraPoints)
                        projCameraPts = hom.projectToAerial(cameraPoints)
                        returnNones(projCameraPts, nones)
                        fillPointQueue(aerialInput.projectedPointQueue, projCameraPts)
                    
                    # if we need to savetxt, do that
                    if aerialInput.needSaveTxt() or cameraInput.needSaveTxt():
                        print "Saving homography to file {} with numpy.savetxt...".format(homographyFilename)
                        hom.savetxt(homographyFilename)
                        aerialInput.saveTxtDone()
                        cameraInput.saveTxtDone()
                    
                    # if we need to add the homography to our list, do that
                    if aerialInput.needSaveHomog() or cameraInput.needSaveHomog():
                        n = time.strftime('%Y%m%d_%H%M%S')
                        print "Recording homography {} in history...".format(n)
                        homographies[n] = hom
                        aerialInput.saveHomogDone()
                        cameraInput.saveHomogDone()
                        
                    # testing points
                    if aerialInput.testProjection.value or cameraInput.testProjection.value:
                        atPoints = drainPointQueue(aerialInput.testPointQueue)
                        if len(atPoints) > 0:
                            ap = atPoints.values()[0]
                            pp = hom.projectToImage(ap, fromAerial=True, objCol=False)[:,0]
                            print "Aerial point {} projects to ({}, {}) in camera frame".format(ap.asTuple(), pp[0], pp[1])
                        ctPoints = drainPointQueue(cameraInput.testPointQueue)
                        if len(ctPoints) > 0:
                            cp = ctPoints.values()[0]
                            pp = hom.projectToWorld(cp, objCol=False)[:,0]
                            print "Point {} in camera frame projects to ({}, {}) in world space".format(cp.asTuple(), pp[0], pp[1])
                        
                
                # if we need to save the points
                if aerialInput.needSavePoints() or cameraInput.needSavePoints():
                    print "Saving to section '{}' of file '{}'...".format(configSection, cfgObj.filename)
                    saveConfig(cfgObj, configSection, aerialImageFile, cameraImageFile, unitsPerPixel, aerialPoints, cameraPoints, homographies)
                    cfgObj.write()                  # write the changes
                    aerialInput.savePointsDone()
                    cameraInput.savePointsDone()
                
                # if we get the quit signal, exit
                if aerialInput.needQuitApp() or cameraInput.needQuitApp():
                    aerialInput.quit()
                    cameraInput.quit()
                
                time.sleep(0.05)
            
            ## once the video is playing, make this session interactive
            #os.environ['PYTHONINSPECT'] = 'Y'           # start interactive/inspect mode (like using the -i option)
            #readline.parse_and_bind('tab:complete')     # turn on tab-autocomplete
        except:
            print traceback.format_exc()
            ret = 1
    sys.exit(ret)
    