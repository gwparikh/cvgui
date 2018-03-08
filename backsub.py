#!/usr/bin/python

import os, sys, time, argparse
import rlcompleter, readline
import cv2
import numpy as np
from cvguipy import cvgui, cvgeom

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
        #self.backSub = cv2.createBackgroundSubtractorMOG2(detectShadows=False)
        self.backSub = cv2.createBackgroundSubtractorKNN(detectShadows=False)
        
    def getForegroundMask(self):
        return self.backSub.apply(self.img)
        
    def getForegroundFrame(self):
        self.fgmask = self.getForegroundMask()
        return cv2.bitwise_and(self.img, self.img, mask=self.fgmask)
    
    def drawExtra(self):
        #self.img = self.getForegroundFrame()
        self.fgimg = self.getForegroundFrame()
        self.img = self.backSub.getBackgroundImage()
    
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
    