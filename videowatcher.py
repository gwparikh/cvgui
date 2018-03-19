#!/usr/bin/env python

import os, sys, time, argparse
import rlcompleter, readline
import multiprocessing, Queue
import numpy as np
import skimage.measure
import cv2
from cvguipy import cvgui, cvgeom

# TODO should use SSIM to compare images
# BUT, should also try using background estimate somehow (maybe SSIM on background? or is that kind of already the same thing? maybe it reduces noise? or then we can isolate the noise? many thoughts....

# TODO make wrapper class that holds 2 images and an SSIM value

def ssimRunner(dataIn, dataOut, alive, n=0, verbose=True):
    """
    Performs an SSIM calculation and deposits the result into a queue,
    allowing it to be run in a separate process.
    
    TODO have option to process individual channels to see in color
    """
    alive.value = True
    while alive.value:
        image1, image2 = dataIn.get()
        grayImage1 = cv2.cvtColor(image1, cv2.COLOR_BGR2GRAY)
        grayImage2 = cv2.cvtColor(image2, cv2.COLOR_BGR2GRAY)
        if verbose:
            print "[{}]: Computing SSIM...".format(n)
            st = time.time()
        ssim = skimage.measure.structural_similarity(grayImage1, grayImage2)
        if verbose:
            print "[{}]: Took {} seconds!".format(n, time.time() - st)
        dataOut.put(ssim)

def meanSquaredError(image1, image2):
    return np.sum((image1.astype("float") - image2.astype("float")) ** 2) / float(image1.shape[0] * image1.shape[1])

class VideoWatcherPlayer(cvgui.cvPlayer):
    def __init__(self, videoFilename, **kwargs):
        super(VideoWatcherPlayer, self).__init__(videoFilename, **kwargs)
        
        #self.firstFrameImage = None
        self.lastSSIMFrame = None
        self.lastTestImage = None
        self.grayImg = None
        self.ssimDataIn = multiprocessing.Queue()
        self.ssimDataOut = multiprocessing.Queue()
        self.ssimThreads = []
        self.ssimThreadSignals = []
        self.startSSIMThreads()
        #print ""
    
    def startSSIMThreads(self):
        for i in range(multiprocessing.cpu_count()):
            a = multiprocessing.Value('i', 1)
            p = multiprocessing.Process(target=ssimRunner, args=(self.ssimDataIn, self.ssimDataOut, a), kwargs={'n': len(self.ssimThreads), 'verbose': True})
            p.daemon = True
            p.start()
            self.ssimThreads.append(p)
            self.ssimThreadSignals.append(a)
    
    def popSSIM(self):
        try:
            return self.ssimDataOut.get(block=False)
        except Queue.Empty:
            pass
    
    def drawExtra(self):
        if self.lastFrameImage is not None:
            #mse = meanSquaredError(self.lastFrameImage, self.image)
            #psnr = 10.0*np.log10((255*255)/mse)
            #psnr1 = None
            #if self.firstFrameImage is not None:
                #mse1 = meanSquaredError(self.firstFrameImage, self.image)
                #psnr1 = 10.0*np.log10((255*255)/mse1)
            #print "{}: psnr: {}   first: {}".format(self.posFrames, psnr, psnr1)
            
            # to use SSIM we need to either use a grayscale image, or process the channels separately
            if self.lastTestImage is None:
                #lb,lg,lr = 
                self.lastTestImage = self.image
            
            # test frames one second (15 frames) apart
            if self.posFrames % 15 == 0:
                self.ssimDataIn.put((self.lastTestImage, self.image))
                #self.runSSIMThread()
                #self.lastTestImage = self.image
                self.lastSSIMFrame = self.posFrames
            
            ssim = self.popSSIM()
            if ssim is not None:
                print "{} (at {}): ssim = {}".format(self.lastSSIMFrame, self.posFrames, ssim)
    
# Entry point
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Play a video, calculating the change in peak signal-to-noise ratio (PSNR) between each frame and the last, and the structural similarity index (SSIM) for a subset of those.")
    parser.add_argument('videoFilename', help="Name of the video file to play.")
    args = parser.parse_args()
    videoFilename = args.videoFilename

    player = VideoWatcherPlayer(videoFilename)
    try:
        player.play()
    #player.pause()
    #player.playInThread()
    # once the video is playing, make this session interactive
    except KeyboardInterrupt:
        os.environ['PYTHONINSPECT'] = 'Y'           # start interactive/inspect mode (like using the -i option)
        readline.parse_and_bind('tab:complete')     # turn on tab-autocomplete
    