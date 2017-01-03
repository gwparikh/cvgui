#!/usr/bin/python
"""Classes for working with homographies easily."""

import os, sys, time, argparse, traceback
import ast
import numpy as np
import multiprocessing, Queue
import imageinput, cvgui, cvgeom
import cv2

class Homography(object):
    """A class containing a homography computed from a set of point
       correspondences taken from an aerial image and a video frame."""
    def __init__(self, aerialPoints=None, cameraPoints=None, unitsPerPixel=1.0):
        self.aerialPoints = cvgeom.ObjectCollection(aerialPoints) if aerialPoints is not None else aerialPoints
        self.cameraPoints = cvgeom.ObjectCollection(cameraPoints) if cameraPoints is not None else cameraPoints
        self.unitsPerPixel = unitsPerPixel
        
        self.aerialPts = None
        self.cameraPts = None
        self.homography = None
        self.inverted = None
        self.mask = None
        self.worldPointDists = None
        self.worldPointSquareDists = None
        self.worldPointError = None
        
    @staticmethod
    def fromString(s, aerialPoints=None, cameraPoints=None, unitsPerPixel=1.0):
        """Load a homography from a string (like [[a,b,c],[d,e,f],[g,h,i]]),
           for instance from a configuration file."""
        hom = Homography(aerialPoints=aerialPoints, cameraPoints=cameraPoints, unitsPerPixel=unitsPerPixel)
        hom.homography = ast.literal_eval(s)
        hom.invert()
        return hom
        
    @staticmethod
    def getObjColFromArray(pArray):
        """Get an ObjectCollection of points from a 2xN array."""
        d = cvgeom.ObjectCollection()
        i = 1
        for x, y in zip(*pArray):
            d[i] = cvgeom.imagepoint(x, y, index=i)
            i += 1
        return d

    @staticmethod
    def getPointArray(points):
        """Get an Nx2 floating-point numpy array from an ObjectCollection of points."""
        a = []
        for i in sorted(points.keys()):
            a.append(points[i].asTuple())
        return np.array(a, dtype=np.float64)
    
    @staticmethod
    def invertHomography(homography):
        invH = np.linalg.inv(homography)
        invH /= invH[2,2]
        return invH
    
    def toString(self):
        if self.homography is not None:
            return str([list(h) for h in self.homography])
    
    def savetxt(self, filename):
        if self.homography is not None:
            np.savetxt(filename, self.homography)
    
    def projectPointArray(self, points, invert=False):
        if len(points) > 0:
            augmentedPoints = np.append(points,[[1]*points.shape[1]], 0)
            hom = self.inverted if invert else self.homography
            prod = np.dot(hom, augmentedPoints)
            return prod[0:2]/prod[2]
        else:
            return np.array([], dtype=np.float64)
    
    def findHomography(self):
        """Compute the homography from the two sets of points and the given units."""
        self.aerialPts = self.unitsPerPixel*Homography.getPointArray(self.aerialPoints)
        self.cameraPts = Homography.getPointArray(self.cameraPoints)
        self.homography, self.mask = cv2.findHomography(self.cameraPts, self.aerialPts)
        self.invert()
        
    def invert(self):
        if self.homography is not None:
            self.inverted = Homography.invertHomography(self.homography)
    
    def projectToAerial(self, points, objCol=True):
        """Project points from image space to the aerial image (without units) for plotting."""
        if self.homography is not None:
            pts = self.projectPointArray(Homography.getPointArray(points).T)/self.unitsPerPixel
            pts = Homography.getObjColFromArray(pts) if objCol else pts
            return pts
    
    def projectToWorld(self, points, objCol=True):
        """Project an ObjectCollection of points in video space to world
           space (in units of unitsPerPixel) using the homography."""
        if self.homography is not None:
            pts = self.projectPointArray(Homography.getPointArray(points).T).T
            pts = Homography.getObjColFromArray(pts) if objCol else pts
            return pts
            
    def projectToImage(self, points, fromAerial=True, objCol=True):
        """Project an ObjectCollection of points from aerial or world space to image space."""
        if self.homography is not None:
            pArray = Homography.getPointArray(points).T
            ipts = pArray*self.unitsPerPixel if fromAerial else pArray
            pts = self.projectPointArray(ipts, invert=True)
            pts = Homography.getObjColFromArray(pts) if objCol else pts
            return pts
    
    def calculateError(self, squared=True):
        """Calculate the error (average of distances (squared, by default) between corresponding points) of
           the homography in world units."""
        # take the aerial points and calculate their position in world coordinates (i.e. multiply by unitsPerPixel)
        worldPts = Homography.getPointArray(self.aerialPoints)*self.unitsPerPixel
        
        # project the camera points to world coordinates with projectToWorld
        projWorldPts = self.projectToWorld(self.cameraPoints, objCol=False)
        
        # calculate the error ([squared] distance) between each pair of points
        self.worldPointDists = np.sqrt(np.sum((worldPts-projWorldPts)**2, axis=1))       # calculate the distance between corresponding points
        self.worldPointSquareDists = self.worldPointDists**2
        
        # average the error values (not summed, so we don't penalize picking more points)
        err = np.sum(self.worldPointSquareDists) if squared else np.sum(self.worldPointDists)
        self.worldPointError = err/len(self.aerialPoints)
        return self.worldPointError
    