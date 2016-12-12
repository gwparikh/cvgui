#!/usr/bin/python
"""A script for running a cvTrajOverlay player with a video, and optionally adding overlay from database of trajectory data.."""

import os, sys, time, argparse, traceback
import rlcompleter, readline
import numpy as np
import threading
import multiprocessing, Queue
import imageinput, cvgui, cvhomog
import cv2

class ProjObjectAdder(imageinput.ObjectAdder):
    """Alternate point adder to reflect changes in projected viewer."""
    def __init__(self, objects, o, projQueue=None):
        super(ProjObjectAdder, self).__init__(objects, o)
        self.projQueue = projQueue
    
    def undo(self):
        # call the ObjectAdder undo then put a None point in the queue
        super(ProjObjectAdder, self).undo()
        self.projQueue.put(imageinput.imagepoint(index=self.o.getIndex()))

class ProjObjectDeleter(imageinput.ObjectDeleter):
    """Alternate point deleter to reflect changes in projected viewer."""
    def __init__(self, objects, dList, projQueue=None):
        super(ProjObjectDeleter, self).__init__(objects, dList)
        self.projQueue = projQueue
    
    def do(self):
        # call the ObjectDeleter do then put a None point in the queue
        super(ProjObjectDeleter, self).do()
        for dList in self.dList:
            for i in dList.keys():
                self.projQueue.put(imageinput.imagepoint(index=i))
        
class HomogInput(imageinput.ImageInput):
    """An ImageInput class for working with homographies, adding the capability to add
       projected points to the image."""
    def __init__(self, imageFilename, configFilename, name=None, printKeys=False, printMouseEvents=None, clickRadius=10, color=None, lineThickness=1):
        # construct ImageInput object
        super(HomogInput, self).__init__(imageFilename, configFilename, name=name, printKeys=printKeys, printMouseEvents=printMouseEvents, clickRadius=clickRadius, color=color, lineThickness=lineThickness)
        
        # homography-specific properties
        self.pointQueue = multiprocessing.Queue()
        self.projectedPointQueue = multiprocessing.Queue()
        self.projectedPoints = imageinput.ObjectCollection()        # collection of points projected from the other image (visible, but can't be manipulated)
        self.recalculate = multiprocessing.Value('b', False)        # flag for GUI to call for recalculating homography
        self.savetxt = multiprocessing.Value('b', False)            # flag for GUI to call for savetxt homography
        
        # extra keybindings
        self.addKeyBindings([262258], 'setRecalculateFlag')         # Ctrl + r - recalculate homography & refresh
        self.addKeyBindings([327763], 'setSaveTxt')                 # Ctrl + Shift + s - homography with numpy savetxt refresh
        
    def setRecalculateFlag(self):
        self.recalculate.value = True
        
    def recalculateDone(self):
        self.recalculate.value = False
       
    def needRecalculate(self):
        return self.recalculate.value
    
    def setSaveTxt(self):
        self.savetxt.value = True
        
    def saveTxtDone(self):
        self.savetxt.value = False
       
    def needSaveTxt(self):
        return self.savetxt.value
    
    def addPoint(self, x, y):
        lastIndx = max(self.points.keys()) if len(self.points) > 0 else 0
        i = lastIndx + 1
        p = imageinput.imagepoint(x, y, i)
        a = ProjObjectAdder(self.points, p, self.pointQueue)
        self.do(a)
        
    def deleteSelected(self):
        """Delete the points from the list, in a way that can be undone."""
        selp = self.selectedPoints()
        a = ProjObjectDeleter(self.points, selp, self.pointQueue)
        selr = self.selectedRegions()
        a.addObjects(self.regions, selr)
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
        
        # call ImageInput's drawFrame to draw the objects owned by this instance
        super(HomogInput, self).drawFrame()
        
        # put our points in the queue
        self.putPoints()
        
        # add the projectedPoints
        self.getProjectedPoints()
        for i, p in self.projectedPoints.iteritems():
            self.drawPoint(p)
        
        # show the updated image
        cv2.imshow(self.windowName, self.img)

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

def projectPointArray(points, homography):
    wasDict = False
    if isinstance(points, dict):
        wasDict = True
        points = getPointArray2N(points)
    augmentedPoints = np.append(points,[[1]*points.shape[1]], 0)
    prod = np.dot(homography, augmentedPoints)
    res = prod[0:2]/prod[2]
    if wasDict:
        return getPointDictFrom2N(res)
    else:
        return res

def getPointDictFrom2N(pArray):
    """Get a dict of points from a 2xN array."""
    d = {}
    i = 1
    for x, y in zip(*pArray):
        d[i] = imageinput.imagepoint(x, y, index=i)
        i += 1
    return d

def getPointArray2N(points):
    """Get a 2xN floating-point numpy array from a dict of points."""
    x, y = [], []
    for i in sorted(points.keys()):
        p = points[i]
        x.append(p.x)
        y.append(p.y)
    return np.array([x,y], dtype=np.float64)

def getPointArray(points):
    """Get an Nx2 floating-point numpy array from a dictionary of points."""
    a = []
    for i in sorted(points.keys()):
        a.append(points[i].asTuple())
    return np.array(a, dtype=np.float64)

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

# Entry point
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Program creating and editing homographies from aerial and camera images and user input.")
    parser.add_argument('-w', dest='aerialImageFile', required=True, help="File containing the aerial image.")
    parser.add_argument('-i', dest='cameraImageFile', required=True, help="File containing a sample camera frame.")
    parser.add_argument('-u', dest='unitsPerPixel', type=float, required=True, help="Units of the aerial image in units/pixel. Should be below 1 (e.g. 0.5 ft/pixel).")
    parser.add_argument('-f', dest='configFilename', help="Name of file containing information about each homography.")
    parser.add_argument('-o', dest='homographyFilename', default='homography.txt', help="Name of file for outputting the final homography (with numpy.savetxt, readable by TrafficIntelligence).")
    parser.add_argument('-pk', dest='printKeys', action='store_true', help="Print keys that are read from the video window (useful for adding shortcuts and other functionality).")
    parser.add_argument('-pm', dest='printMouseEvents', type=int, nargs='*', help="Print mouse events that are read from the video window (useful for adding other functionality). Optionally can provide a number, which signifies the minimum event flag that will be printed.")
    parser.add_argument('-r', dest='clickRadius', type=int, default=10, help="Radius of clicks on the image (in pixels).")
    #parser.add_argument('-i', dest='interactive', action='store_true', help="Show the image in a separate thread and start an interactive shell.")
    args = parser.parse_args()
    aerialImageFile = args.aerialImageFile
    cameraImageFile = args.cameraImageFile
    unitsPerPixel = args.unitsPerPixel
    configFilename = args.configFilename
    homographyFilename = args.homographyFilename
    interactive = True
    hom = None
    ret = 0
    
    # create the ImageInput objects
    # TODO Ctrl + Shift + Q to quit all
    aerialInput = HomogInput(aerialImageFile, configFilename, printKeys=args.printKeys, printMouseEvents=args.printMouseEvents, clickRadius=args.clickRadius)
    cameraInput = HomogInput(cameraImageFile, configFilename, printKeys=args.printKeys, printMouseEvents=args.printMouseEvents, clickRadius=args.clickRadius)
    
    # get the signals (multiprocessing.Value objects to communicate between processes)
    aSig = aerialInput.getAliveSignal()
    cSig = cameraInput.getAliveSignal()
    
    # show the windows
    aerialInput.showInThread()
    time.sleep(2)
    cameraInput.showInThread()
    
    try:
        while aSig.value and cSig.value:
            aPoints = drainPointQueue(aerialInput.pointQueue)
            cPoints = drainPointQueue(cameraInput.pointQueue)
            
            # TODO process the points - compute homography if 4 or more points, project points and put into projectedPointQueue
            # TODO something not working here (extra points? - updating problem, how is it handling point moves/additions/deletions and unequal # points?)....
            if hom is None or aerialInput.needRecalculate() or cameraInput.needRecalculate():
                if len(aPoints) >= 4 and len(cPoints) >= 4:
                    if len(aPoints) == len(cPoints):
                        hom = cvhomog.Homography(aPoints, cPoints, unitsPerPixel)
                aerialInput.recalculateDone()
                cameraInput.recalculateDone()
                
            if hom is not None:
                # if we have points, project them
                if len(aPoints) > 0:
                    nones = holdNones(aPoints)
                    projAerialPts = hom.projectToImage(aPoints, fromAerial=True)
                    returnNones(projAerialPts, nones)
                    fillPointQueue(cameraInput.projectedPointQueue, projAerialPts)
                if len(cPoints) > 0:
                    nones = holdNones(cPoints)
                    projCameraPts = hom.projectToAerial(cPoints)
                    returnNones(projCameraPts, nones)
                    fillPointQueue(aerialInput.projectedPointQueue, projCameraPts)
                
                # if we need to savetxt, do that
                if aerialInput.needSaveTxt() or cameraInput.needSaveTxt():
                    print "Saving homography to file {} with numpy.savetxt...".format(homographyFilename)
                    hom.savetxt(homographyFilename)
                aerialInput.saveTxtDone()
                cameraInput.saveTxtDone()
                
                # TODO saving the homography!! (see htestcfg.cfg)
            
                # TODO calculating error
            time.sleep(0.05)
        
        ## once the video is playing, make this session interactive
        #os.environ['PYTHONINSPECT'] = 'Y'           # start interactive/inspect mode (like using the -i option)
        #readline.parse_and_bind('tab:complete')     # turn on tab-autocomplete
    except:
        print traceback.format_exc()
        ret = 1
        
    finally:
        sys.exit(ret)
    