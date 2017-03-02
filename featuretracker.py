#!/usr/bin/python

"""
Experimentations with feature tracking. Working towards the following paper:

Kanhere, Neeraj K., and Stanley T. Birchfield. "Real-time incremental segmentation and tracking of vehicles at low camera angles using stable features." IEEE Transactions on Intelligent Transportation Systems 9.1 (2008): 148-160. cecas.clemson.edu/~stb/publications/vehicle_tracking_its2008.pdf.

Notes
======
+ Uses background subtraction to isolate moving objects
+ Identifies corners in the image to seed feature tracker
+ Uses Lucas-Kanade feature tracker to track features across frames
+ Uses background mask to project points to ground and determine stable/unstable features (see Kanhere, et. al)

"""

# TODO collect all adjustable parameters, work on some calibration techniques/tools
# TODO implement grouping of features to create vehicle hypotheses

import os, sys, time, argparse
import rlcompleter, readline
import multiprocessing
import cv2
import numpy as np
import cvgui, cvgeom

def getFirstRunOfSize(bits, minSize=2):
    """
    Return the index of the beginning of the first run of length
    greater than minSize in binary/logical array bits.
    """
    bits = np.array(bits, dtype=np.int32)               # make integers
    
    # make sure all runs of ones are well-bounded
    bounded = np.hstack(([0], bits, [0]))
    
    # get 1 at run starts and -1 at run ends
    difs = np.diff(bounded)
    runStarts, = np.where(difs > 0)
    runEnds, = np.where(difs < 0)
    runLens = runEnds - runStarts
    
    # return the index of the first run that is long enough
    longEnough = runLens > minSize
    if np.any(longEnough):
        return runStarts[longEnough][0]

class Point(object):
    def __init__(self, x, y):
        self.x = x
        self.y = y
    
    def __repr__(self):
        return "({}, {})".format(self.x, self.y)
    
    def __eq__(self, p):
        return self.x == p.x and self.y == p.y
    
    def __add__(self, p):
        return Point(self.x + p.x, self.y + p.y)
    
    def __sub__(self, p):
        return Point(self.x - p.x, self.y - p.y)
    
    def __neg__(self, p):
        return Point(-self.x, -self.y)
    
    def __mul__(self, s):
        return Point(self.x*s, self.y*s)
    
    def __div__(self, s):
        return Point(self.x/s, self.y/s)
    
    def asTuple(self):
        return (self.x, self.y)
    
    def norm2(self):
        return np.sqrt(self.norm2Squared())
    
    def norm2Squared(self):
        return self.x**2 + self.y**2

class Track(object):
    def __init__(self, trackId, color=None, smoothingWindow=5):
        self.trackId = trackId
        self.color = color if color is not None else cvgui.randomColor()
        self.smoothingWindow = smoothingWindow
        self.points = []
        self.velocity = []
        self.lastVel = None
        self.lastPos = None
        self.smoothedVel = None
    
    def __repr__(self):
        return "[{}]: {}".format(self.trackId, self.points)
        
    def numPoints(self):
        return len(self.points)
        
    def addPoint(self, x, y):
        self.lastPos = Point(x, y)
        if len(self.points) > 0:
            self.lastVel = (self.lastPos - self.points[-1])
            self.velocity.append(self.lastVel)
        self.points.append(self.lastPos)
        
    def removeOldest(self):
        self.points.pop(0)
    
    def pointArray(self, dtype=None):
        return np.array([p.asTuple() for p in self.points], dtype=dtype)
    
class featureTrackerPlayer(cvgui.cvPlayer):
    def __init__(self, videoFilename, detectShadows=True, removeShadows=True, detectionInterval=5, **kwargs):
        super(featureTrackerPlayer, self).__init__(videoFilename, fps=15.0, **kwargs)
        
        self.detectShadows = detectShadows
        self.removeShadows = removeShadows
        self.lastFrameDrawn = -1
        self.fgmask = None
        self.fgframe = None
        self.grayImg = None
        self.times = []
        self.frameQueue = multiprocessing.Queue()
        self.fgmaskQueue = multiprocessing.Queue()
        self.backSubThread = None
        self.trackerThread = None
        self.tStart = time.time()
        
        # params for feature detector
        self.maxCorners = 1000
        self.qualityLevel = 0.01
        self.minDistance = 5
        self.blockSize = 7
        self.maxTrackLength = np.inf
        self.detectionInterval = detectionInterval              # limit detection to keep noise down
        self.lastDetectionFrame = -1
        
        # params for feature tracker
        self.winSize  = (15, 15)
        self.maxLevel = 2
        self.criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 10, 0.03)         # termination criteria
        self.minFeatureTime = 3                                                             # minimum length of trajectory to accept feature for keeping
        self.tracks = []
        
        # for classifying features
        self.roadAngle = None
        
    def open(self):
        self.openWindow()
        self.openVideo()
        self.readFrame()
        
        # get angle of road from line in config file
        self.loadConfig()
        if len(self.objects) > 0:
            # transverse line across road
            lobj = self.objects['transverse'] if 'transverse' in self.objects else None
            if lobj is not None and len(lobj.points) == 2:
                p1, p2 = lobj.points.values()
                d = p2 - p1
                rho, self.roadAngle = cvgeom.cart2pol(d.x, d.y)
            
            # read detection region mask
            detreg = self.objects['detection_region'] if 'detection_region' in self.objects else None
            self.detectionRegion = None
            if detreg is not None:
                pts = np.array([detreg.points[i].asTuple() for i in sorted(detreg.points.keys())])
                self.detectionRegion = np.uint8(cv2.fillConvexPoly(np.zeros((self.imgHeight,self.imgWidth)),pts,255))
            
            # remove objects so they aren't drawn on the image
            self.objects = cvgeom.ObjectCollection()
        
        # start background subtractor
        #self.backSub = cv2.createBackgroundSubtractorMOG2(detectShadows=self.detectShadows)
        self.backSub = cv2.createBackgroundSubtractorKNN(detectShadows=self.detectShadows)
        
    def getForegroundMask(self):
        """
        Use the background subtractor to generate a foreground mask, then
        apply a Gaussian filter to remove small patches of background.
        """
        fgmask = self.backSub.apply(self.img)
        return cv2.GaussianBlur(fgmask, (11, 11), 0)
    
    def getForegroundFrame(self):
        self.fgmask = self.getForegroundMask()
        if self.removeShadows:
            self.fgmask[self.fgmask==127] = 0
        self.img = cv2.bitwise_and(self.img, self.img, mask=self.fgmask)
    
    def getGrayImage(self):
        if self.grayImg is not None:
            self.lastGrayImage = self.grayImg.copy()
        mimg = self.img if self.detectionRegion is None else cv2.bitwise_and(self.img, self.img, mask=self.detectionRegion)
        self.grayImg = cv2.cvtColor(mimg, cv2.COLOR_BGR2GRAY)
    
    def resetTracks(self):
        """Clear targets to reset the feature tracker (after jumps and stuff)"""
        self.tracks = []
    
    def getNewTracks(self):
        """Get new features from the current frame and add them to our targets."""
        corners = cv2.goodFeaturesToTrack(self.grayImg, mask=self.detectionRegion, maxCorners=self.maxCorners, qualityLevel=self.qualityLevel, minDistance=self.minDistance, blockSize=self.blockSize)
        if corners is not None:
            for x, y in np.float32(corners).reshape(-1, 2):
                # make a new track with the next ID number
                tid = len(self.tracks)
                t = Track(tid)
                t.addPoint(x,y)
                #print t
                self.tracks.append(t)
        self.lastDetectionFrame = self.posFrames
    
    def trackFeatures(self):
        """Track features across frames. Most of this is from OpenCV's lk_track.py example."""
        # get a grayscale image for the feature detector/tracker
        self.getGrayImage()
        
        # if it's the first frame, or if we just jumped backwards, or if we jumped ahead (more than one frame ahead of last frame drawn)
        if self.lastFrameDrawn == -1 or self.lastFrameDrawn > self.posFrames or (self.posFrames-self.lastFrameDrawn) > 1:
            self.resetTracks()          # reset the feature tracker
        
        # if we have any tracks, track them into the new frame (we'll hit this on the 2nd time around)
        if len(self.tracks) > 0:
            p0 = np.float32([tr.points[-1].asTuple() for tr in self.tracks]).reshape(-1, 1, 2)
            #print p0
            
            # track forwards
            p1, st, err = cv2.calcOpticalFlowPyrLK(self.lastGrayImage, self.grayImg, p0, None, winSize=self.winSize, maxLevel=self.maxLevel, criteria=self.criteria)
            
            # track backwards
            p0r, st, err = cv2.calcOpticalFlowPyrLK(self.grayImg, self.lastGrayImage, p1, None, winSize=self.winSize, maxLevel=self.maxLevel, criteria=self.criteria)
            
            # compare motion between the two - they shouldn't differ much (I think that's what this does)
            d = abs(p0-p0r).reshape(-1, 2).max(-1)
            goodTracks = d < 1
            
            # add new points to our tracks
            newTracks = []
            for tr, (x, y), goodFlag in zip(self.tracks, p1.reshape(-1, 2), goodTracks):
                if not goodFlag:
                    continue            # only keep the good ones
                tr.addPoint(x, y)
                if tr.numPoints() > self.maxTrackLength:
                    tr.removeOldest()               # trim tracks that are too long
                newTracks.append(tr)
            self.tracks = newTracks
        
        # if it's the first frame, or it's been detectionInterval frames since the last detection, detect some new features
        if self.lastDetectionFrame == -1 or (self.posFrames-self.lastDetectionFrame) >= self.detectionInterval:
            self.getNewTracks()
        
    def drawTrack(self, t, perturb=20):
        """Draw a track as a line leading up to a point."""
        if len(t.points) >= self.minFeatureTime and t.lastVel is not None and t.lastVel.norm2() > 1:
            # TODO move most of this to another method
            r = int(round(t.lastPos.y))
            c = int(round(t.lastPos.x))
            cl = max(0,c-perturb)
            cr = min(self.fgmask.shape[1]-1,c+perturb)
            dl = self.fgmask[r:,cl]
            dm = self.fgmask[r:,c]
            dr = self.fgmask[r:,cr]
            bg = 0
            msz = 5
            if bg in dl and bg in dr:
                # project down from the feature point, and perturb left and right
                il = getFirstRunOfSize(dl==bg, minSize=msz)
                im = getFirstRunOfSize(dm==bg, minSize=msz)
                ir = getFirstRunOfSize(dr==bg, minSize=msz)
                if all([il,im,ir]):
                    # check angle of the resulting line WRT the road transverse line to group
                    # the features as stable (front/back of vehicles, closer to the ground),
                    # and unstable (sides of vehicles)
                    ix = cr - cl
                    iy = ir - il
                    rho, phi = cvgeom.cart2pol(ix, iy)
                    angleToRoad = cvgeom.rad2deg(phi-self.roadAngle)
                    if abs(angleToRoad) < 10:
                        # uncomment to draw trajectories as lines
                        #cv2.polylines(self.img, [t.pointArray(dtype=np.int32)], False, t.color, thickness=2)
                        
                        # draw stable features in blue
                        if len(t.points) >= 1:
                            p = t.points[-1]
                            # if drawing from Track object
                            #self.drawPoint(cvgeom.imagepoint(p.x, p.y, index=t.trackId, color=t.color))
                            #cv2.circle(self.img, p.asTuple(), 4, cvgui.getColorCode('blue'), thickness=4)
                            cv2.circle(self.img, tuple(map(int, (c,r))), 4, cvgui.getColorCode('blue'), thickness=4)
                    # draw unstable features in red
                    else:
                        if len(t.points) >= 1:
                            p = t.points[-1]
                            #cv2.circle(self.img, p.asTuple(), 4, cvgui.getColorCode('red'), thickness=4)
                            cv2.circle(self.img, tuple(map(int, (c,r))), 4, cvgui.getColorCode('red'), thickness=4)
                
                # TODO group features, etc.
        
    def makeAvgTime(self, tElapsed):
        if len(self.times) > 20:
            self.times.pop(0)
        self.times.append(tElapsed)
        return np.mean(self.times)
        
    def drawExtra(self):
        # track features
        self.trackFeatures()
        
        # get a foreground mask & frame
        self.getForegroundFrame()
        
        #self.img = self.fgframe.copy()
        
        # plot all the tracks
        if len(self.tracks) > 0:
            #print len(self.tracks)
            for t in self.tracks:
                self.drawTrack(t)
                
        self.lastFrameDrawn = self.posFrames
    
# Entry point
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Simple test of feature tracking with background extraction.")
    parser.add_argument('videoFilename', help="Name of the video file to play.")
    parser.add_argument('-f', dest='configFile', help="Name of the config file containing geometry.")
    parser.add_argument('-s', dest='configSection', help="Section of the config file containing geometry to load.")
    args = parser.parse_args()
    videoFilename = args.videoFilename

    player = featureTrackerPlayer(videoFilename, configFilename=args.configFile, configSection=args.configSection)
    try:
        player.play()
    #player.pause()
    #player.playInThread()
    # once the video is playing, make this session interactive
    except KeyboardInterrupt:
        os.environ['PYTHONINSPECT'] = 'Y'           # start interactive/inspect mode (like using the -i option)
        readline.parse_and_bind('tab:complete')     # turn on tab-autocomplete
    