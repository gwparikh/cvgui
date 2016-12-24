#!/usr/bin/python
"""A script for running a cvTrajOverlay player with a video, and optionally adding overlay from database of trajectory data.."""

import os, sys, time, argparse, traceback
from configobj import ConfigObj
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
        self.projQueue.put(cvgui.imagepoint(index=self.o.getIndex()))

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
                self.projQueue.put(cvgui.imagepoint(index=i))
        
class HomogInput(imageinput.ImageInput):
    """An ImageInput class for working with homographies, adding the capability to add
       projected points to the image."""
    def __init__(self, imageFilename, name=None, printKeys=False, printMouseEvents=None, clickRadius=10, color=None, lineThickness=1):
        # construct ImageInput object
        super(HomogInput, self).__init__(imageFilename, configFilename=None, printKeys=printKeys, printMouseEvents=printMouseEvents, clickRadius=clickRadius, color=color, lineThickness=lineThickness)
        
        # homography-specific properties
        self.pointQueue = multiprocessing.Queue()
        self.projectedPointQueue = multiprocessing.Queue()
        self.projectedPoints = cvgui.ObjectCollection()             # collection of points projected from the other image (visible, but can't be manipulated)
        self.recalculate = multiprocessing.Value('b', False)        # flag for GUI to call for recalculating homography
        self.savetxt = multiprocessing.Value('b', False)            # flag for GUI to call for savetxt homography
        self.savePts = multiprocessing.Value('b', False)            # flag for GUI to call for saving all info (reuses Ctrl + S as shortcut)
        self.saveHomog = multiprocessing.Value('b', False)          # flag for GUI to call for saving the homography to the history
        self.quitApp = multiprocessing.Value('b', False)            # flag for GUI to call for quitting the entire application
        self.homographies = {}                                      # a list of all the homographies we have calculated
        self.error = multiprocessing.Value('f', -1)                 # error in world units (-1 if not set)
        
        # extra keybindings
        self.addKeyBindings([262258], 'setRecalculateFlag')         # Ctrl + r - recalculate homography & refresh
        self.addKeyBindings([327763], 'setSaveTxt')                 # Ctrl + Shift + s - save homography with numpy savetxt
        self.addKeyBindings([262248], 'setSaveHomog')               # Ctrl + h - save homography in dict
        self.addKeyBindings([327761], 'setQuitApp')                 # Ctrl + Shift + q - quit application
        
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
    
    def setSaveHomog(self):
        self.saveHomog.value = True
    
    def saveHomogDone(self):
        self.saveHomog.value = False
    
    def needSaveHomog(self):
        return self.saveHomog.value
    
    def savePoints(self):
        """Set the flag to save points."""
        self.savePts.value = True
        
    def savePointsDone(self):
        self.savePts.value = False
    
    def needSavePoints(self):
        return self.savePts.value
    
    def setQuitApp(self):
        self.quitApp.value = True
        
    def needQuitApp(self):
        return self.quitApp.value
    
    def addPoint(self, x, y):
        lastIndx = max(self.points.keys()) if len(self.points) > 0 else 0
        i = lastIndx + 1
        p = cvgui.imagepoint(x, y, i)
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
        
        # add the error if we have it
        if self.haveError():
            eStr = "Error = {} world units squared".format(round(self.getError(), 3))
            self.drawText(eStr, 11, 31, fontSize=2)
        
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
                aerialPoints = cvgui.ObjectCollection()
                for i, p in cfg['points']['aerialPoints'].iteritems():
                    aerialPoints[int(i)] = cvgui.imagepoint(int(p[0]), int(p[1]), index=int(i))
            if 'cameraPoints' in cfg['points']:
                cameraPoints = cvgui.ObjectCollection()
                for i, p in cfg['points']['cameraPoints'].iteritems():
                    cameraPoints[int(i)] = cvgui.imagepoint(int(p[0]), int(p[1]), index=int(i))
        if 'homographies' in cfg:
            homographies = {}
            for d, hom in cfg['homographies'].iteritems():
                homographies[d] = cvhomog.Homography.fromString(hom, aerialPoints=aerialPoints, cameraPoints=cameraPoints, unitsPerPixel=unitsPerPixel)
    else:
        print "ConfigObj section {} not found!".format(name)
    return aerialImageFile, cameraImageFile, unitsPerPixel, aerialPoints, cameraPoints, homographies

# Entry point
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Program creating and editing homographies from aerial and camera images and user input.")
    parser.add_argument('-w', dest='aerialImageFile', help="File containing the aerial image.")
    parser.add_argument('-i', dest='cameraImageFile', help="File containing a sample camera frame.")
    parser.add_argument('-u', dest='unitsPerPixel', type=float, required=True, help="Units of the aerial image in units/pixel. Should be below 1 (e.g. 0.5 ft/pixel).")
    parser.add_argument('-f', dest='configFilename', help="Name of file containing saved data.")
    parser.add_argument('-n', dest='configSection', help="Name of section of file where data is saved")
    parser.add_argument('-o', dest='homographyFilename', default='homography.txt', help="Name of file for outputting the final homography (with numpy.savetxt, readable by TrafficIntelligence).")
    parser.add_argument('-pk', dest='printKeys', action='store_true', help="Print keys that are read from the video window (useful for adding shortcuts and other functionality).")
    parser.add_argument('-pm', dest='printMouseEvents', type=int, nargs='*', help="Print mouse events that are read from the video window (useful for adding other functionality). Optionally can provide a number, which signifies the minimum event flag that will be printed.")
    parser.add_argument('-r', dest='clickRadius', type=int, default=10, help="Radius of clicks on the image (in pixels).")
    #parser.add_argument('-i', dest='interactive', action='store_true', help="Show the image in a separate thread and start an interactive shell.")
    args = parser.parse_args()
    configFilename = args.configFilename
    configSection = args.configSection
    homographyFilename = args.homographyFilename
    interactive = True
    hom = None
    ret = 0
    
    # create a configobj so we can load/save info
    cfgObj = ConfigObj(configFilename)
    
    aerialImageFile, cameraImageFile, unitsPerPixel, aerialPoints, cameraPoints, homographies = loadConfig(cfgObj, configSection)
    
    # override the file names and units per pixel read in the config if provided in the command
    aerialImageFile = args.aerialImageFile if args.aerialImageFile is not None else aerialImageFile
    cameraImageFile = args.cameraImageFile if args.cameraImageFile is not None else cameraImageFile
    unitsPerPixel = args.unitsPerPixel if unitsPerPixel is None else unitsPerPixel
    
    # create the ImageInput objects
    aerialInput = HomogInput(aerialImageFile, configFilename, printKeys=args.printKeys, printMouseEvents=args.printMouseEvents, clickRadius=args.clickRadius)
    cameraInput = HomogInput(cameraImageFile, configFilename, printKeys=args.printKeys, printMouseEvents=args.printMouseEvents, clickRadius=args.clickRadius)
    
    # get the signals (multiprocessing.Value objects to communicate between processes)
    aSig = aerialInput.getAliveSignal()
    cSig = cameraInput.getAliveSignal()
    
    # set the points in the HomogInputs if we read some from the config
    if isinstance(aerialPoints, cvgui.ObjectCollection):
        aerialInput.points = aerialPoints
    if isinstance(cameraPoints, cvgui.ObjectCollection):
        cameraInput.points = cameraPoints
    
    # set the homographies or create a new dict
    homographies = {} if homographies is None else homographies
    
    # show the windows
    aerialInput.showInThread()
    time.sleep(2)
    cameraInput.showInThread()
    
    try:
        aerialPoints = cvgui.ObjectCollection()
        cameraPoints = cvgui.ObjectCollection()
        while aSig.value and cSig.value:
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
                        hom.findHomography()
                        error = hom.calculateError(squared=True)
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
            
            # if we need to save the points
            if aerialInput.needSavePoints() or cameraInput.needSavePoints():
                print "Saving..."
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
        
    finally:
        sys.exit(ret)
    