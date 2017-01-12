#!/usr/bin/python

import os, sys, time, argparse
import rlcompleter, readline
import cv2
import numpy as np
import cvgui, cvgeom

class bsubPlayer(cvgui.cvPlayer):
    def __init__(self, videoFilename):
        super(bsubPlayer, self).__init__(videoFilename, fps=10000.0)
        
        self.maxCorners = 1000
        self.qualityLevel = 0.01
        self.minDistance = 5
        
        self.fgmask = None
        self.fgframe = None
        
    def open(self):
        self.openWindow()
        self.openVideo()
        self.startBackSub()
        
    def startBackSub(self):
        self.backSub = cv2.createBackgroundSubtractorMOG2(detectShadows=False)
        
    def getForegroundMask(self):
        return self.backSub.apply(self.img)
        
    def getForegroundFrame(self):
        self.fgmask = self.getForegroundMask()
        return cv2.bitwise_and(self.img, self.img, mask=self.fgmask)
    
    def getForegroundFeatures(self):
        self.fgframe = self.getForegroundFrame()
        grayimg = cv2.cvtColor(self.img, cv2.COLOR_BGR2GRAY)
        
        # TODO - define ImageFeature class, construct one from each corner
        # - have a pool of workers take the features and foreground mask and find the PLP of the feature and two adjacent points
        
        return cv2.goodFeaturesToTrack(grayimg, self.maxCorners, self.qualityLevel, self.minDistance, mask=self.fgmask)
    
    def detectDrawCorners(self):
        # detect strong corners
        self.corners = self.getForegroundFeatures()
        
        # plot all the corners
        if self.corners is not None:
            cid = 0
            #self.img = self.fgframe        # uncomment this to plot on foreground only
            for c in self.corners:
                cx, cy = c[0]
                self.drawPoint(cvgeom.imagepoint(cx, cy, index=cid, color='random'))
                cid += 1
        
    def drawFrame(self):
        img = self.getForegroundFrame()
        # show the image
        cv2.imshow(self.windowName, img)
        #self.isPaused = True           # uncomment to pause at every frame

# Entry point
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Simple test of background extraction.")
    parser.add_argument('videoFilename', help="Name of the video file to play.")
    args = parser.parse_args()
    videoFilename = args.videoFilename

    player = bsubPlayer(videoFilename)
    player.play()
    player.pause()
    #player.playInThread()
    # once the video is playing, make this session interactive
    #os.environ['PYTHONINSPECT'] = 'Y'           # start interactive/inspect mode (like using the -i option)
    #readline.parse_and_bind('tab:complete')     # turn on tab-autocomplete
    