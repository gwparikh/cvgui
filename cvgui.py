#!/usr/bin/python
"""Classes and functions for developing interactive GUI utilities based on OpenCV's highgui modules."""

import os, sys, time, argparse, traceback
import random, math
import threading, multiprocessing
import rlcompleter, readline
import numpy as np
import shapely.geometry
import cv2
import cvgeom

# check opencv version for compatibility 
if cv2.__version__[0] == '2':
    # enums have different names
    cvFONT_HERSHEY_PLAIN = cv2.cv.CV_FONT_HERSHEY_PLAIN
    cvCAP_PROP_FRAME_WIDTH = cv2.cv.CV_CAP_PROP_FRAME_WIDTH
    cvCAP_PROP_FRAME_HEIGHT = cv2.cv.CV_CAP_PROP_FRAME_HEIGHT
    cvCAP_PROP_FRAME_COUNT = cv2.cv.CV_CAP_PROP_FRAME_COUNT
    cvCAP_PROP_FPS = cv2.cv.CV_CAP_PROP_FPS
    cvCAP_PROP_POS_AVI_RATIO = cv2.cv.CV_CAP_PROP_POS_AVI_RATIO
    cvCAP_PROP_POS_FRAMES = cv2.cv.CV_CAP_PROP_POS_FRAMES
    cvCAP_PROP_POS_MSEC = cv2.cv.CV_CAP_PROP_POS_MSEC
    
    # original waitKey function fine in opencv 2
    cvWaitKey = cv2.waitKey
elif cv2.__version__[0] == '3':
    cvFONT_HERSHEY_PLAIN = cv2.FONT_HERSHEY_PLAIN
    cvCAP_PROP_FRAME_WIDTH = cv2.CAP_PROP_FRAME_WIDTH
    cvCAP_PROP_FRAME_HEIGHT = cv2.CAP_PROP_FRAME_HEIGHT
    cvCAP_PROP_FRAME_COUNT = cv2.CAP_PROP_FRAME_COUNT
    cvCAP_PROP_FPS = cv2.CAP_PROP_FPS
    cvCAP_PROP_POS_AVI_RATIO = cv2.CAP_PROP_POS_AVI_RATIO
    cvCAP_PROP_POS_FRAMES = cv2.CAP_PROP_POS_FRAMES
    cvCAP_PROP_POS_MSEC = cv2.CAP_PROP_POS_MSEC
    
    # but was 'fixed' in 3 (gives same results across OS, but modifiers stripped off - we need to use waitKeyEx)
    cvWaitKey = cv2.waitKeyEx

cvColorCodes = {'red': (0,0,255),
                'orange': (0,153,255),
                'yellow': (0,255,255),
                'green': (0,255,0),
                'forest': (0,102,0),
                'cyan': (255,255,0),
                'blue': (255,0,0),
                'indigo': (255,0,102),
                'violet': (204,0,102),
                'pink': (255,0,255),
                'magenta': (153,0,204),
                'brown': (0,51,102),
                'burgundy': (51,51,153),
                'white': (255,255,255),
                'black': (0,0,0)}

def randomColor(whiteOK=True, blackOK=True):
    colors = dict(cvColorCodes)
    if not whiteOK:
        colors.pop('white')
    if not blackOK:
        colors.pop('black')
    return colors.values()[random.randint(0,len(cvColorCodes)-1)]

def getColorCode(color, default='blue', whiteOK=True, blackOK=True):
        if isinstance(color, str):
            if color in cvColorCodes:
                return cvColorCodes[color]
            elif color.lower() == 'random':
                return randomColor(whiteOK, blackOK)
            elif color.lower() == 'default':
                return cvColorCodes[default]
            elif ',' in color:
                try:
                    return tuple(map(int, color.strip('()').split(',')))            # in case we got a string tuple representation
                except:
                    print "Problem loading color {} . Please check your inputs.".format(color)
        elif isinstance(color, tuple) and len(color) == 3:
            try:
                return tuple(map(int, color))           # in case we got a tuple of strings
            except ValueError or TypeError:
                print "Problem loading color {} . Please check your inputs.".format(color)
        else:
            return cvColorCodes[default]

def getKey(key):
    """Take a key code from cv2.waitKey, convert it into an ASCII character if possible, otherwise just return the int."""
    if key >= 0 and key <= 255:
        return chr(key)
    else:
        return key

class KeyCode(object):
    """An object representing a press of one or more keys, meant to
       correspond to a function (or specifically, a class method).
       
       This class handles the complex key codes from cv2.waitKeyEx,
       which includes the bit flags that correspond to modifiers
       keys. This allows you to set key combinations with simple
       strings like 'ctrl + shift + d'.
       
       Key code strings must include at least one printable ASCII
       character, preceded by 0 or more modifier strings, with the
       key values separated by '+' characters (can be changed with
       the delim argument). Any modifiers following the ASCII key
       are ignored.
       
       A class method is provided to clear the NumLock flag from a 
       key code if it is present, since it is generally handled 
       correctly by the keyboard driver. Currently this is the
       only modifier that is removed, but if similar unexpected
       behavior is encountered with other lock keys (e.g. function
       lock, which I don't have on a keyboard now), it will likely
       be handled similarly (if it makes sense to do so).
       
       The class also handles characters so the Shift modifier is
       automatically handled (so Ctrl + Shift + A == Ctrl + Shift + a).
    """
    # modifier flags
    MODIFIER_FLAGS = {}
    MODIFIER_FLAGS['SHIFT'] =   0x010000
    MODIFIER_FLAGS['CTRL'] =    0x040000
    MODIFIER_FLAGS['ALT'] =     0x080000
    MODIFIER_FLAGS['SUPER'] =   0x400000
    
    # lock flags to remove
    LOCK_FLAGS = {}
    LOCK_FLAGS['NUMLOCK'] = 0x100000
    LOCK_FLAGS['CAPSLOCK'] = 0x20000
    
    # special keys
    SPECIAL_KEYS = {}
    SPECIAL_KEYS['DEL'] = 0xffff
    SPECIAL_KEYS['BACKSPACE'] = 0x8
    SPECIAL_KEYS['ENTER'] = 10
    SPECIAL_KEYS['ESC'] = 27
    #KEY_F1 = 0xffbe
       
    def __init__(self, codeString, delim='+'):
        # parse the code string to extract the info we need
        # first split on delim
        keyStrs = codeString.split(delim)
        self.delim = delim.strip()
        
        # loop through the key strings to create our key code
        self.code = 0
        self.codeStrings = []
        self.codeString = None
        key = None
        for ks in keyStrs:
            # check for modifiers (but only add them once)
            if ks.strip().upper() in self.MODIFIER_FLAGS:
                ksu = ks.strip().upper()
                mf = self.MODIFIER_FLAGS[ksu]
                if self.code & mf != mf:
                    # add to the code and to the string list
                    self.code += mf
                    self.codeStrings.append(ksu.capitalize())
            # check for keys (end our loop
            # special keys
            elif ks.strip().upper() in self.SPECIAL_KEYS:
                key = ks.strip().upper()
                break
            # printable ASCII codes (assumed to be first single character)
            elif len(ks.strip()) == 1:
                key = ks.strip()
                break
            elif ks == ' ':
                key = ks
                break
            else:
                # if we got anything else, we can't do anything
                self.code = None
                return
        # if we got a key, use it
        if key is not None:
            if key not in self.SPECIAL_KEYS:
                # take the ord if it's not a special key
                kc = ord(key)
                # make sure it's printable, otherwise we can't do it
                if kc >= 32 and kc < 127:
                    # now check if we got a shift flag, to know if we need to use the upper or lower
                    if self.code & self.MODIFIER_FLAGS['SHIFT'] == self.MODIFIER_FLAGS['SHIFT']:
                        key = key.upper()
                    else:
                        key = key.lower()
                    keycode = ord(key)
                    self.codeStrings.append(key)
            else:
                # otherwise just use the code we have
                keycode = self.SPECIAL_KEYS[key]
            # add the keycode to the code and generate the string
            self.code += keycode
            self.codeString = " {} ".format(self.delim).join(self.codeStrings)
        else:
            # if we didn't get a key, we can't do anything
            self.code = None
    
    def __repr__(self):
        return "<KeyCode '{}' = {}>".format(self.codeString, self.code)
    
    def __hash__(self):
        return self.code
    
    def __eq__(self, code):
        """Test if 'code' matches our code."""
        return self.code == code
    
    @classmethod
    def clearLocks(cls, code):
        """Remove any of the LOCK_FLAGS present in the key code."""
        for lf in cls.LOCK_FLAGS.values():
            if code & lf == lf:
                return (code - lf)
        return code
    
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

class cvGUI(object):
    """A class for handling interactions with OpenCV's GUI tools.
       Most of this is documented here:
         http://docs.opencv.org/2.4/modules/highgui/doc/user_interface.html
    """
    def __init__(self, filename=None, fps=15.0, name=None, printKeys=False, printMouseEvents=None, clickRadius=10, lineThickness=1, textFontSize=4.0):
        # constants
        self.filename = filename
        self.fps = float(fps)
        self.iFPS = int(round((1/self.fps)*1000))
        self.name = filename if name is None else name
        self.printKeys = printKeys
        self.printMouseEvents = printMouseEvents
        self.clickRadius = clickRadius
        self.lineThickness = lineThickness
        self.textFontSize = textFontSize
        self.windowName = None
        
        # important variables and containers
        self.alive = multiprocessing.Value('b', True)               # this can cross processes
        self.thread = None
        self.actionBuffer = []              # list of user actions
        self.undoneActions = []             # list of undone actions, which fills as actions are undone
        self.lastKey = None
        self.img, self.image = None, None       # image and a copy
        self.creatingObject = None
        
        # mouse and keyboard functions are registered by defining a function in this class (or one based on it) and inserting it's name into the mouseBindings or keyBindings dictionaries
        self.mouseBindings = {}                         # dictionary of {event: methodname} for defining mouse functions
        self.keyBindings = {}                           # dictionary of {keyCode: methodname} for defining key bindings
        
        # default bindings:
        
        # TODO - add a method (script) for 'learning' key codes based on user input to get around waitKey issue (we will probably need to adjust the model we are using here to associate key codes with functions, inserting an additional translation step to take machine-specific in
        
        self.addKeyBindings(['f'], 'advanceOne')
        self.addKeyBindings(['Ctrl + Q'], 'quit')
        self.addKeyBindings(['Ctrl + Z'], 'undo')
        self.addKeyBindings(['Ctrl + Shift + Z', 'Ctrl + Y'], 'redo')
    
    def __repr__(self):
        return "<{}: {}>".format(self.__class__.__name__, self.name)
        
    def isAlive(self):
        return self.alive.value
    
    def getAliveSignal(self):
        return self.alive
        
    def addKeyBindings(self, keyCodeList, funName):
        """Add a keybinding for each of the key code strings in keyCodeList to trigger method funName."""
        if not isinstance(keyCodeList, list):
            keyList = [keyCodeList]
        for k in keyCodeList:
            # create a KeyCode object from the string and use it as the key
            kc = KeyCode(k)
            self.keyBindings[kc] = funName
    
    def addMouseBindings(self, eventList, funName):
        """Add a mouse binding for each of the events in eventList to trigger method funName."""
        if not isinstance(eventList, list):
            eventList = [eventList]
        for k in eventList:
            self.mouseBindings[k] = funName
    
    def run(self):
        print "{} -- please override the run() method to show/play/whatever your GUI app!".format(self)
        while self.isAlive():
            self.readKey(cvWaitKey(self.iFPS))
    
    def runInThread(self, useProcess=True):
        """Run in a separate thread or process."""
        ps = 'thread'
        if useProcess:
            ps = 'process'
            self.thread = multiprocessing.Process(target=self.run)
        else:
            self.thread = threading.Thread(target=self.run)
        print "{} running in separate {}...".format(self, ps)
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
        if self.printMouseEvents is not None and (event in self.printMouseEvents or (len(self.printMouseEvents) > 0 and self.printMouseEvents[0] < 0)):
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
            key = KeyCode.clearLocks(key)           # clear any modifier flags from NumLock
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
        
    def showFrame(self):
        """Show the image in the player."""
        if self.img is not None:
            cv2.imshow(self.windowName, self.img)
    
    def clear(self):
        """Clear everything from the image."""
        if self.img is not None:
            self.img = self.image.copy()
        
    # plotting functions
    # only makes sense if we have an image, but we will need these regardless of the type of image
    #def drawFrame(self):
        #"""Show the image in the player."""
        #if self.img is not None:
            #cv2.imshow(self.windowName, self.img)
    
    def drawText(self, text, x, y, fontSize=None, color='green', thickness=2):
        fontSize = self.textFontSize if fontSize is None else fontSize
        color = getColorCode(color, default='green')
        cv2.putText(self.img, str(text), (x,y), cvFONT_HERSHEY_PLAIN, fontSize, color, thickness=thickness)
    
    def drawPoint(self, p):
        """Draw the point on the image as a circle with crosshairs."""
        ct = 4*self.lineThickness if p.selected else self.lineThickness                 # highlight the circle if it is selected
        cv2.circle(self.img, p.asTuple(), self.clickRadius, p.color, thickness=ct)       # draw the circle
        
        # draw the line from p.x-self.clickRadius to p.x+clickRadius
        p1x, p2x = p.x - self.clickRadius, p.x + self.clickRadius
        cv2.line(self.img, (p1x, p.y), (p2x, p.y), p.color, thickness=1)
        
        # draw the line from p.x-self.clickRadius to p.x+clickRadius
        p1y, p2y = p.y - self.clickRadius, p.y + self.clickRadius
        cv2.line(self.img, (p.x, p1y), (p.x, p2y), p.color, thickness=1)
        
        # add the index of the point to the image
        cv2.putText(self.img, str(p.index), p.asTuple(), cvFONT_HERSHEY_PLAIN, self.textFontSize, p.color, thickness=2)
        
    def drawObject(self, obj):
        """Draw a cvgeom.MultiPointObject on the image as a linestring. If it is selected, 
           draw it as a linestring with a thicker line and points drawn as 
           selected points (which can be "grabbed")."""
        dlt = 2*self.lineThickness
        lt = 4*dlt if obj.selected else dlt
        points = np.array([obj.pointsForDrawing()], dtype=np.int32)
        isClosed = isinstance(obj, cvgeom.imageregion) and obj != self.creatingObject
        
        # draw the lines as polylines
        cv2.polylines(self.img, points, isClosed, obj.color, thickness=lt)
        
        # and also draw the points if selected
        for p in obj.points.values():
            if obj.selected or p.selected:
                self.drawPoint(p)
            
        # add the index at whatever the min point is
        if len(obj.points) > 0:
            p = obj.points[obj.points.getFirstIndex()]
            cv2.putText(self.img, str(obj.index), p.asTuple(), cvFONT_HERSHEY_PLAIN, 4.0, obj.color, thickness=2)
        
        
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
        self.video = None
        
        # key/mouse bindings
        # self.keyBindings[<code>] = 'fun'                  # method 'fun' must take key code as only required argument
        # self.mouseBindings[<event code>] = 'fun'          # method 'fun' must take event, x, y, flags, param as arguments
        
        # default bindings:
        self.addKeyBindings([' '], 'pause')          # Spacebar - play/pause video
        
    def open(self):
        """Open the video."""
        # open a window (which also sets up to read keys and mouse clicks) and the video (which also sets up the trackbar)
        self.openWindow()
        self.openVideo()
        
    def isOpened(self):
        if hasattr(self, 'video') and self.video is not None:
            return self.video.isOpened()
        else:
            return False
    
    def openVideo(self):
        try:
            # open the video capture object
            self.video = cv2.VideoCapture(self.videoFilename)
            
            # get information about the video
            self.vidWidth = int(self.video.get(cvCAP_PROP_FRAME_WIDTH))
            self.vidHeight = int(self.video.get(cvCAP_PROP_FRAME_HEIGHT))
            self.nFrames = int(self.video.get(cvCAP_PROP_FRAME_COUNT))
            self.fps = float(self.video.get(cvCAP_PROP_FPS))
            self.iFPS = int(round((1/self.fps)*1000))
            
            # set up the frame trackbar, going from 0 to nFrames
            self.trackbarValue = 0
            self.trackbarName = 'Frame'
            
            # trackbar callback function
            def jumpToFrame(tbPos):
                self.jumpToFrame(tbPos)
            cv2.createTrackbar(self.trackbarName, self.windowName, self.trackbarValue, self.nFrames, jumpToFrame)
        except:
            print traceback.format_exc()
            print "Error encountered when opening video file '{}'. Please check that the video file exists. If it does and this still doesn't work, you may be missing the FFMPEG library files, which requires recompiling OpenCV to fix.".format(self.videoFilename)
            sys.exit(1)
        
    def getVideoPosFrames(self):
        """Get the current position in the video in frames."""
        self.updateVideoPos()
        return self.posFrames

    def updateVideoPos(self):
        """Update values containing current position of the video player in %, frame #, and msec."""
        self.posAviRatio = float(self.video.get(cvCAP_PROP_POS_AVI_RATIO))
        self.posFrames = int(self.video.get(cvCAP_PROP_POS_FRAMES))
        self.posMsec = int(self.video.get(cvCAP_PROP_POS_MSEC))
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
            #print "posFrames: {}, tbPos: {}".format(self.posFrames, tbPos)
            #self.video.set(cvCAP_PROP_POS_FRAMES, tbPos)
            
            # TODO NOTE - this is a workaround until we can find a better way to deal with the frame skipping bug in OpenCV (see: http://code.opencv.org/issues/4081)
            if tbPos < self.posFrames:
                self.video.set(cvCAP_PROP_POS_FRAMES, 0)
                self.updateVideoPos()
            for i in range(0,self.tbPos-self.posFrames):
                self.frameOK, self.image = self.video.read()
                self.img = self.image.copy()
                    
            #frameTime = 1000.0 * tbPos/self.fps
            #self.video.set(cvCAP_PROP_POS_MSEC, frameTime)
            self.readFrame()
            self.drawFrame()
        
    def readFrame(self):
        """Read a frame from the video capture object."""
        if self.video.isOpened():
            self.frameOK, self.image = self.video.read()
            if self.frameOK:
                self.img = self.image.copy()
                self.trackbarValue += 1
                self.updateVideoPos()
                self.updateTrackbar()
            return self.frameOK
        return self.video.isOpened()
    
    def clearFrame(self):
        """Clear the current frame (i.e. to remove lines drawn on the image)."""
        self.clear()
        
    def advanceOne(self):
        """Move the video ahead a single frame."""
        self.readFrame()
        self.drawFrame()
        
    def drawFrame(self):
        """Show the frame in the player."""
        cv2.imshow(self.windowName, self.img)
        
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
            self.readKey(cvWaitKey(self.iFPS))
            
    def pause(self, key=None):
        """Toggle play/pause the video."""
        self.isPaused = not self.isPaused
        
    def update(self):
        """Update (redraw) the current frame to reflect changes."""
        self.clearFrame()
        self.drawFrame()
    
class cvImage(cvGUI):
    """A class for displaying images using OpenCV's highgui features.
    """
    def __init__(self, imageFilename, fps=15.0, name=None, printKeys=False, printMouseEvents=None, clickRadius=10, lineThickness=1, textFontSize=4.0):
        # construct cvGUI object
        super(cvImage, self).__init__(filename=imageFilename, fps=fps, name=name, printKeys=printKeys, printMouseEvents=printMouseEvents, clickRadius=clickRadius, lineThickness=lineThickness, textFontSize=textFontSize)
        
        # image-specific properties
        self.imageFilename = imageFilename
        self.imageBasename = os.path.basename(imageFilename)
        self.imageThread = None
        self.imgWidth, self.imgHeight, self.imgDepth = None, None, None
        
        # key/mouse bindings
        # self.keyBindings[<code>] = 'fun'                  # method 'fun' must take key code as only required argument
        # self.mouseBindings[<event code>] = 'fun'          # method 'fun' must take event, x, y, flags, param as arguments
        
        # TODO - add this properly
        self.keyBindings[327618] = 'clear'                  # Ctrl + F5 to clear image
    
    def openImage(self):
        """Read the image file into an array."""
        print "Opening image {}".format(self.imageFilename)
        self.image = cv2.imread(self.imageFilename)
        self.imgHeight, self.imgWidth, self.imgDepth = self.image.shape
        self.img = self.image.copy()
        
    def open(self):
        """Open a window and the image file."""
        self.openWindow()
        self.openImage()
        
    def isOpened(self):
        return self.image is not None
        
    def run(self):
        """Alternate name for show (to match cvGUI class)."""
        self.show()
    
    def showInThread(self):
        """Show the image in a separate thread."""
        self.runInThread()
        
    def show(self):
        """Show the image in an interactive interface."""
        self.alive.value = True
        
        # open the image first if necessary
        if not self.isOpened():
            self.open()
        
        while self.isAlive():
            # showing the image and reading keys
            self.drawFrame()
            self.readKey(cvWaitKey(self.iFPS))
            
    def drawFrame(self):
        self.showFrame()
    
    def update(self):
        """Update (redraw) the current frame to reflect a change."""
        self.clear()
        self.drawFrame()
    