#!/usr/bin/python
"""Classes and functions for developing interactive GUI utilities based on OpenCV's highgui modules."""

import os, sys, time, argparse, traceback
import random
import rlcompleter, readline
import cv2
import numpy as np
import threading
import multiprocessing

cvColorCodes = {'red': (0,0,255),
                'green': (0,255,0),
                'blue': (255,0,0),
                'cyan': (255, 255, 0),
                'yellow': (0, 255, 255),
                'magenta': (255, 0, 255),
                'white': (255, 255, 255),
                'black': (0,0,0)}

def randomColor(whiteOK=True, blackOK=True):
    colors = dict(cvColorCodes)
    if not whiteOK:
        colors.pop('white')
    if not blackOK:
        colors.pop('black')
    return colors.values()[random.randint(0,len(cvColorCodes)-1)]

def getKey(key):
    """Take a key code from cv2.waitKey, convert it into an ASCII character if possible, otherwise just return the int."""
    if key >= 0 and key <= 255:
        return chr(key)
    else:
        return key

def getFrameObjectList(objects):
    frameObjects = {}
    for o in objects:
        for i in o.timeInterval:
            if i not in frameObjects:
                frameObjects[i] = []
            frameObjects[i].append(o)
    return frameObjects

class action(object):
    """A dummy class for representing an action that can be done and undone.
       To make an action for a cvGUI-dependent class, create a class based
       on the action class then:
          + override the constructor (and any other functions) to accept all 
            inputs the action will require
          + override the do() method, which must perfor all necessary actions
            to "do" the action
          + (optionally) override the undo() method, which should perform all
            necessary actions to undo an action
        Such an action can then be used by a method in a cvGUI-dependent class
        to implement a function that can be undone and re-done easily.
    """
    def __init__(self, name=None):
        self.name = name
        
    def __repr__(self):
        return "<action: {} -- {}>".format(self.__class__.__name__, self.name)
    
    def do(self):
        print "This action has not implemented to do() method, so it does nothing!"
    
    def undo(self):
        print "This action cannot be undone!"
        
# TODO - make a generic cvGUI class that handles window interactions, a cvPlayer class based on cvGUI for playing videos, a cvImage class based on cvGUI for interacting with still images (not videos), a cvOverlayPlayer (or similar name) class based on cvPlayer that does everything that cvPlayer currently does, and a cvImageSelector class for selecting points (maybe split into homography-creation class and polygon-selecting class

class cvGUI(object):
    """A class for handling interactions with OpenCV's GUI tools.
       Most of this is documented here:
         http://docs.opencv.org/2.4/modules/highgui/doc/user_interface.html
    """
    def __init__(self, filename=None, fps=15.0, name=None, printKeys=False, printMouseEvents=None):
        # constants
        self.filename = filename
        self.fps = fps
        self.iFPS = int(round((1/self.fps)*1000))
        self.name = filename if name is None else name
        self.printKeys = printKeys
        self.printMouseEvents = printMouseEvents
        self.windowName = None
        
        # important variables and containers
        self.alive = multiprocessing.Value('b', True)               # this can cross processes
        self.thread = None
        self.actionBuffer = []              # list of user actions
        self.undoneActions = []             # list of undone actions, which fills as actions are undone
        self.lastKey = None
        
        # mouse and keyboard functions are registered by defining a function in this class (or one based on it) and inserting it's name into the mouseBindings or keyBindings dictionaries
        self.mouseBindings = {}                         # dictionary of {event: methodname} for defining mouse functions
        self.keyBindings = {}                           # dictionary of {keyCode: methodname} for defining key bindings
        
        # default bindings:
        self.addKeyBindings([102], 'advanceOne')                            # f - advance one frame
        self.addKeyBindings([262257,1310833], 'quit')                       # Ctrl + q - quit
        self.addKeyBindings([262266,1310842], 'undo')                       # Ctrl + z - undo last action
        self.addKeyBindings([327770,262265,1310841,1376346], 'redo')        # Ctrl + Shift + z / Ctrl + y - redo last undone action
    
    def __repr__(self):
        return "<{}: {}>".format(self.__class__.__name__, self.name)
        
    def isAlive(self):
        return self.alive.value
    
    def getAliveSignal(self):
        return self.alive
        
    def addKeyBindings(self, keyList, funName):
        """Add a keybinding for each of the keys in keyList to trigger method funName."""
        if not isinstance(keyList, list):
            keyList = [keyList]
        for k in keyList:
            self.keyBindings[k] = funName
    
    def addMouseBindings(self, eventList, funName):
        """Add a mouse binding for each of the events in eventList to trigger method funName."""
        if not isinstance(eventList, list):
            eventList = [eventList]
        for k in eventList:
            self.mouseBindings[k] = funName
    
    def run(self):
        print "{} -- please override the run() method to show/play/whatever your GUI app!".format(self)
        while self.isAlive():
            self.readKey(cv2.waitKey(self.iFPS))
    
    def runInThread(self):
        """Run in a separate thread."""
        print "{} running in separate thread...".format(self)
        self.thread = multiprocessing.Process(target=self.run)
        self.thread.start()
        
    def quit(self, key=None):
        self.alive.value = False
        cv2.destroyWindow(self.windowName)
        
    def open(self):
        self.openWindow()
    
    def close(self):
        self.quit()
    
    def openWindow(self, windowName=None):
        """Open the video player window."""
        # Relies primarily on openCV's namedWindow function (see here for more info: http://docs.opencv.org/2.4/modules/highgui/doc/user_interface.html#namedwindow)
        
        # generate the window name from the player's name (or passed as parameter)
        # NOTE: window name is window handle
        self.windowName = str(self) if windowName is None else windowName
        
        # create the window
        cv2.namedWindow(self.windowName, cv2.WINDOW_NORMAL)      # WINDOW_NORMAL = resizable window
        
        # set up to read mouse clicks
        # mouse callback function
        def readMouse(event, x, y, flags, param):
            self.readMouse(event, x, y, flags, param)
        cv2.setMouseCallback(self.windowName, readMouse)
        
    def readMouse(self, event, x, y, flags, param):
        if self.printMouseEvents is not None and event >= self.printMouseEvents:
            print "<Mouse Event {} at ({}, {}), flags={} param={}".format(event, x, y, flags, param)
        if event in self.mouseBindings:
            # if we have a function registered to this event, call it
            funName = self.mouseBindings[event]
            fun = getattr(self, funName)
            try:
                fun(event, x, y, flags, param)
            except TypeError:
                ## try it with no arguments
                #try:
                    #fun()
                #except:
                print traceback.format_exc()
                print "readMouse: Method {} not implemented correctly".format(fun)

    def readKey(self, key):
        # if less than 0, ignore it NOTE: -1 is what we get when waitKey times out. is there any way to differentiate it from the window's X button??
        self.lastKey = key
        if key >= 0:
            redraw = False
            if self.printKeys:
                print "<Key = {}>".format(key)
            if key in self.keyBindings:
                # if we have a key binding registered, get the method tied to it and call it
                funName = self.keyBindings[key]
                fun = getattr(self, funName)
                try:
                    fun(key)
                except TypeError:
                    # try it with no argument
                    try:
                        fun()
                    except:
                        print traceback.format_exc()
                        print "readKey: Method {} not implemented correctly".format(fun)
               
    def update(self):
        """Update everything in the GUI object to reflect a change (must be overrided,
           by default this does nothing)."""
        pass
    
    def do(self, a):
        """Do an action and put it in the action buffer so it can be undone."""
        if isinstance(a, action):
            a.do()
        else:
            print "Do: action '{}' is not implemented correctly!!".format(a)
        self.actionBuffer.append(a)
        
        # clear the redo buffer
        self.undoneActions = []
        
        # update to reflect changes
        self.update()
    
    def did(self, a):
        """Inform the object that an action has been performed, so it can be added
           to the action buffer. Useful if you want to draw something out as it is done
           in real time, but have undo/redo actions happen instantly."""
        self.actionBuffer.append(a)
        self.update()
    
    def undo(self, key=None):
        """Undo actions in the action buffer."""
        if len(self.actionBuffer) > 0:
            a = self.actionBuffer.pop()
            if isinstance(a, action):
                a.undo()
                self.undoneActions.append(a)
            else:
                print "Undo: action '{}' is not implemented correctly!!".format(a)
                self.actionBuffer.append(a)
        
        # update to reflect changes
        self.update()
    
    def redo(self, key=None):
        """Redo actions in the action buffer."""
        if len(self.undoneActions) > 0:
            a = self.undoneActions.pop()
            if isinstance(a, action):
                a.do()
                self.actionBuffer.append(a)
            else:
                print "Redo: action '{}' is not implemented correctly!!".format(a)
                self.undoneActions.append(a)
        
        # update to reflect changes
        self.update()
    
    def forget(self, key=None):
        """Remove a single action from the undo buffer, but forget about it forever."""
        if len(self.undoneActions) > 0:
            self.actionBuffer.pop()
    
    def clearActions(self, key=None):
        """Clear the action buffer and undone actions."""
        self.actionBuffer = []
        self.undoneActions = []
        
class cvPlayer(cvGUI):
    """A class for playing a video using OpenCV's highgui features. Uses the cvGUI class
       to handle keyboard and mouse input to the window. To create a player for a 
       particular purpose, create a new class based on the cvPlayer class and override
       any methods you would like to change. Then define any functions you need to handle
       keyboard/mouse input and set a keyboard/mouse binding by adding an entry to the
       keyBindings or mouseBindings dictionaries in the form:
           {<key /mouse event code>: 'functionName'}
       These are inherited from the cvGUI class, which binds the key/mouse codes to
       the appropriate method.
       NOTE:
        + A method for a key event must accept they key code as its only argument.
        + A method for a mouse event must accept 5 arguments: event, x, y, flags, param
       
       The cvPlayer class adds interactive video playing capabilities to the cvGUI
       class, using an OpenCV VideoCapture object to read a video file and play it
       in a window with a trackbar. The position of the video can be changed using
       the trackbar and also Ctrl+Left/Right.
    """
    def __init__(self, videoFilename, fps=15.0, name=None, printKeys=False, printMouseEvents=None):
        # construct cvGUI object
        super(cvPlayer, self).__init__(filename=videoFilename, fps=fps, name=name, printKeys=printKeys, printMouseEvents=printMouseEvents)
        
        # video-specific properties
        self.videoFilename = videoFilename
        self.frameOK = True
        self.currFrame = 0
        self.trackbarValue = 0
        self.isPaused = False
        
        # key/mouse bindings
        # self.keyBindings[<code>] = 'fun'                  # method 'fun' must take key code as only required argument
        # self.mouseBindings[<event code>] = 'fun'          # method 'fun' must take event, x, y, flags, param as arguments
        
        # default bindings:
        self.addKeyBindings([32,1048608], 'pause')          # Spacebar - play/pause video
        
    def open(self):
        """Open the video."""
        # open a window (which also sets up to read keys and mouse clicks) and the video (which also sets up the trackbar)
        self.openWindow()
        self.openVideo()
        
    def isOpened(self):
        if hasattr(self, 'video'):
            return self.video.isOpened()
        else:
            return False
    
    def openVideo(self):
        # open the video capture object
        self.video = cv2.VideoCapture(self.videoFilename)
        
        # get information about the video
        self.vidWidth = int(self.video.get(cv2.cv.CV_CAP_PROP_FRAME_WIDTH))
        self.vidHeight = int(self.video.get(cv2.cv.CV_CAP_PROP_FRAME_HEIGHT))
        self.nFrames = int(self.video.get(cv2.cv.CV_CAP_PROP_FRAME_COUNT))
        self.fps = float(self.video.get(cv2.cv.CV_CAP_PROP_FPS))
        self.iFPS = int(round((1/self.fps)*1000))
        
        # set up the frame trackbar, going from 0 to nFrames
        self.trackbarValue = 0
        self.trackbarName = 'Frame'
        
        # trackbar callback function
        def jumpToFrame(tbPos):
            self.jumpToFrame(tbPos)
        cv2.createTrackbar(self.trackbarName, self.windowName, self.trackbarValue, self.nFrames, jumpToFrame)
        
    def getVideoPosFrames(self):
        """Get the current position in the video in frames."""
        self.updateVideoPos()
        return self.posFrames

    def updateVideoPos(self):
        """Update values containing current position of the video player in %, frame #, and msec."""
        self.posAviRatio = float(self.video.get(cv2.cv.CV_CAP_PROP_POS_AVI_RATIO))
        self.posFrames = int(self.video.get(cv2.cv.CV_CAP_PROP_POS_FRAMES))
        self.posMsec = int(self.video.get(cv2.cv.CV_CAP_PROP_POS_MSEC))
        #print "posFrames: {}, posMsec: {}, posAviRatio: {}".format(self.posFrames, self.posMsec, self.posAviRatio)
        
    def updateTrackbar(self):
        """Update the position of the indicator on the trackbar to match the current frame."""
        cv2.setTrackbarPos(self.trackbarName, self.windowName, self.posFrames)
        
    def jumpToFrame(self, tbPos):
        """Trackbar callback (i.e. video seek) function. Seeks forward or backward in the video
           corresponding to manipulation of the trackbar."""
        #if tbPos >= 60:
            #tbPos = tbPos + 12
           
        self.updateVideoPos()
        self.tbPos = tbPos
        if tbPos != self.posFrames:
            #m = tbPos % 30
            print "posFrames: {}, tbPos: {}".format(self.posFrames, tbPos)
            #self.video.set(cv2.cv.CV_CAP_PROP_POS_FRAMES, tbPos)
            
            # TODO NOTE - this is a workaround until we can find a better way to deal with the frame skipping bug in OpenCV (see: http://code.opencv.org/issues/4081)
            if tbPos < self.posFrames:
                self.video.set(cv2.cv.CV_CAP_PROP_POS_FRAMES, 0)
                self.updateVideoPos()
            for i in range(0,self.tbPos-self.posFrames):
                self.frameOK, self.videoFrame = self.video.read()
                self.frameImg = self.videoFrame.copy()
                    
            #frameTime = 1000.0 * tbPos/self.fps
            #self.video.set(cv2.cv.CV_CAP_PROP_POS_MSEC, frameTime)
            self.readFrame()
            self.drawFrame()
        
    def readFrame(self):
        """Read a frame from the video capture object."""
        if self.video.isOpened():
            self.frameOK, self.videoFrame = self.video.read()
            if self.frameOK:
                self.frameImg = self.videoFrame.copy()
                self.trackbarValue += 1
                self.updateVideoPos()
                self.updateTrackbar()
            return self.frameOK
        return self.video.isOpened()
    
    def clearFrame(self):
        """Clear the current frame (i.e. to remove lines drawn on the image)."""
        self.frameImg = self.videoFrame.copy()
        
    def advanceOne(self):
        """Move the video ahead a single frame."""
        self.readFrame()
        self.drawFrame()
        
    def drawFrame(self):
        """Show the frame in the player."""
        cv2.imshow(self.windowName, self.frameImg)
        
    def run(self):
        """Alternate name for play (to match cvGUI class)."""
        self.play()
        
    def playInThread(self):
        self.runInThread()
        
    def play(self):
        """Play the video."""
        self.alive.value = True
        
        # open the video first if necessary
        if not self.isOpened():
            self.open()
        
        while self.isAlive():
            # keep showing frames and reading keys
            if not self.isPaused:
                self.frameOK = self.readFrame()
                self.drawFrame()
            self.readKey(cv2.waitKey(self.iFPS))
            
    def pause(self, key):
        """Toggle play/pause the video."""
        self.isPaused = not self.isPaused
        
    def update(self):
        """Update (redraw) the current frame to reflect changes."""
        self.clearFrame()
        self.drawFrame()
    
class cvImage(cvGUI):
    """A class for displaying images using OpenCV's highgui features.
    """
    def __init__(self, imageFilename, name=None, printKeys=False, printMouseEvents=None):
        # construct cvGUI object
        super(cvImage, self).__init__(filename=imageFilename, name=name, printKeys=printKeys, printMouseEvents=printMouseEvents)
        
        # image-specific properties
        self.imageFilename = imageFilename
        self.imageBasename = os.path.basename(imageFilename)
        self.imageThread = None
        
        # key/mouse bindings
        # self.keyBindings[<code>] = 'fun'                  # method 'fun' must take key code as only required argument
        # self.mouseBindings[<event code>] = 'fun'          # method 'fun' must take event, x, y, flags, param as arguments
        self.keyBindings[327618] = 'clear'                  # Ctrl + F5 to clear image
    
    def openImage(self):
        """Read the image file into an array."""
        self.image = cv2.imread(self.imageFilename)
        self.img = self.image.copy()
        
    def open(self):
        """Open a window and the image file."""
        self.openWindow()
        self.openImage()
        
    def isOpened(self):
        return hasattr(self, 'image')
        
    def run(self):
        """Alternate name for show (to match cvGUI class)."""
        self.show()
        
    #def quit(self, key=None):
        #super(cvImage, self).quit(key)
        #if isinstance(self.imageThread, multiprocessing.Process):
            #self.imageThread.terminate()
        
    def showInThread(self):
        """Show the image in a separate thread."""
        self.runInThread()
        
    def show(self):
        """Show the image in an interactive interface."""
        self.alive.value = True
        
        # open the video first if necessary
        if not self.isOpened():
            self.open()
        
        while self.isAlive():
            # showing the image and reading keys
            self.drawFrame()
            self.readKey(cv2.waitKey(self.iFPS))
            
    def drawFrame(self):
        """Show the image in the player."""
        cv2.imshow(self.windowName, self.img)
        
    def clear(self):
        """Clear everything from the image."""
        self.img = self.image.copy()
      
    def update(self):
        """Update (redraw) the current frame to reflect a change."""
        self.clear()
        self.drawFrame()
    