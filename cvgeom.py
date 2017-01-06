#!/usr/bin/python

"""Classes and methods for geometry operations."""

import os, sys, time, traceback
import numpy as np
import shapely.geometry
import scipy.interpolate
import cvgui

def cart2pol(x, y):
    rho = np.sqrt(x**2 + y**2)
    phi = np.arctan2(y, x)
    return(rho, phi)

def pol2cart(rho, phi):
    x = rho * np.cos(phi)
    y = rho * np.sin(phi)
    return(x, y)

class IndexableObject(object):
    """An indexable-object that can be named and selected."""
    def __init__(self, index=None, name=''):
        self.index = index
        self.name = name
        self.selected = False
    
    def __repr__(self):
        return "<{}>".format(self.getObjStr)
    
    def getObjStr(self):
        s = "{} {}".format(self.__class__.__name__, self.getNameStr())
        return s
    
    def getNameStr(self):
        s = "{}".format(self.index)
        if len(self.name) > 0:
            s += " ({})".format(self.name)
        return s
    
    def getIndex(self):
        return self.index
    
    def setIndex(self, i):
        indx = i
        for t in [int, float]:
            try:                    # try to get a numerical value so we can sort on this index
                indx = t(i)
            except ValueError or TypeError:
                pass
        self.index = i          # default to string if all else
    
    def getName(self):
        return self.name
    
    def setName(self, n):
        self.name = str(n)
    
    def shiftUp(self, inc=1):
        """Increment the index by inc (default 1)."""
        self.index += inc
    
    def shiftDown(self, inc=1):
        """Decrement the index by inc (default 1)."""
        self.index -= inc
    
    def select(self):
        self.selected = True
        
    def deselect(self):
        self.selected = False
        
    def toggleSelected(self):
        # call the methods so they can be overridden
        if self.selected:
            self.deselect()
        else:
            self.select()
    
class PlaneObject(IndexableObject):
    """A class representing a geometric object in a plane."""
    def __init__(self, index=None, name='', color='random'):
        super(PlaneObject, self).__init__(index=index, name=name)
        self.setColor(color)
        self.selected = False
        self.shapelyObj = None
    
    def setColor(self, color):
        self.color = cvgui.getColorCode(color)
    
    def distance(self, o):
        """Calculate the distance between ourself and object o (relies on the genShapelyObj method)."""
        self.genShapelyObj()
        o.genShapelyObj()
        if self.shapelyObj is not None and o.shapelyObj is not None:
            return self.shapelyObj.distance(o.shapelyObj)            # gives distance from the point to the closest point on the boundary, whether it's inside or outside
    
    def asShapely(self):
        self.genShapelyObj()
        return self.shapelyObj
    
    def asTuple(self):
        print "The asTuple method has not been implemented for class '{}' !".format(self.__class__.__name__)
    
    def genShapelyObj(self):
        print "The genShapelyObj method has not been implemented for class '{}' !".format(self.__class__.__name__)

class imagepoint(PlaneObject):
    """A class representing a point selected on an image.  Coordinates are stored as
       integers to correspond with pixel coordinates."""
    def __init__(self, x=None, y=None, index=None, color='random', name=''):
        super(imagepoint, self).__init__(index=index, name=name, color=color)
        
        self.x = int(round(x)) if x is not None else x
        self.y = int(round(y)) if y is not None else y
        self.index = index
        self.selected = False
        
    def __repr__(self):
        return "<{}: ({}, {})>".format(self.getObjStr(), self.x, self.y)
        
    def __add__(self, p):
        return imagepoint(self.x+p.x, self.y+p.y)

    def __sub__(self, p):
        return imagepoint(self.x-p.x, self.y-p.y)
    
    def __neg__(self):
        return imagepoint(-self.x, -self.y)
    
    def isNone(self):
        return self.x is None or self.y is None
        
    def asTuple(self):
        return (int(self.x), int(self.y))
    
    def asList(self):
        return [self.x, self.y]
    
    def genShapelyObj(self):
        if self.x is not None and self.y is not None:
            self.shapelyObj = shapely.geometry.Point(self.x, self.y)
    
    def pushBack(self):
        self.index += 1
        
    def pullForward(self):
        self.index -= 1
        
    def move(self, p):
        self.x += p.x
        self.y += p.y
        
    def moveTo(self, p):
        self.x = p.x
        self.y = p.y
    
    def rotate(self, o, dPhi):
        rho, phi = cart2pol(self.x-o.x, self.y-o.y)
        self.x, self.y = pol2cart(rho, phi + dPhi)
    
class MultiPointObject(PlaneObject):
    """A class representing a multi-point object, defined as an ordered
       collection of points."""
    def __init__(self, index=None, name='', color='random'):
        super(MultiPointObject, self).__init__(index=index, name=name, color=color)
        
        self.points = ObjectCollection()
        self.selected = False
        
    def __repr__(self):
        return "<{}: {}>".format(self.getObjStr(), self.points)
    
    def toLatLon(self, proj, imgLat, imgLon, unitsPerPixel):
        """Project all points to lat/lon given the pyproj object proj, assuming that 
           the upper-left corner of the image is located at imgLat, imgLon"""
        # first translate the image coordinates to the new XY coordinate system
        pointsXY = self.toProjXY(proj, imgLat, imgLon, unitsPerPixel)
        
        # then project all the points to lat/lon using the (inverse) projection object
        pointsLatLon = {}
        for i, p in pointsXY.iteritems():
            x, y = p
            lon, lat = proj(x, y, inverse=True)
            pointsLatLon[i] = (lat,lon)
        return pointsLatLon
    
    def toProjXY(self, proj, imgLat, imgLon, unitsPerPixel=1.0):
        """Translate all points to the coordinate system given by pyproj object proj,
           assuming the upper-left corner of the image is located at imgLat and imgLon."""
        # first get the image coordinates in the X,Y system
        imgX, imgY = proj(imgLon, imgLat)
        
        # now go through all the points and calculate their positions (i.e. offset by imgX, imgY)
        points = {}
        for i, p in self.points.iteritems():
            px = imgX + p.x*unitsPerPixel                 # add x coordinate
            py = imgY - p.y*unitsPerPixel                 # but need to reverse y coordinate (image convention -> cartesian)
            points[i] = (px, py)
        return points
    
    def move(self, dp):
        """Move the object by moving all points in the object."""
        for p in self.points.values():
            p.move(dp)
    
    def asTuple(self):
        pList = []
        for p in self.points.values():
            pList.append(p.asTuple())
        return tuple(pList)
        
    def pointsForDrawing(self):
        return self.asTuple()
        
    def genShapelyObj(self):
        """Make a shapely MultiPoint object."""
        if len(self.points) > 0:
            self.shapelyObj = shapely.geometry.MultiPoint(self.asTuple())
    
    def select(self):
        self.selected = True
        for p in self.points.values():
            p.select()
    
    def deselect(self):
        self.selected = False
        for p in self.points.values():
            p.deselect()
        
    def selectedPoints(self):
        return {i: p for i, p in self.points.iteritems() if p.selected}
        
    def getInsertIndex(self, x, y, clickRadius=10):
        """Get the index to insert the point between the 2 points that
           make up the line that it is closest to."""
        cp = imagepoint(x, y)
        indx = None
        if len(self.points) >= 2:             # we need at least two points to insert it
            # loop over point pairs
            indeces = sorted(self.points.keys())
            p1, p2 = None, None
            for i in range(0, len(indeces)-1):
                p1 = self.points[indeces[i]]
                p2 = self.points[indeces[i+1]]
                line = shapely.geometry.LineString([p1.asTuple(), p2.asTuple()])
                if line.distance(cp.asShapely()) < clickRadius:
                    indx = indeces[i+1]
                    break
            if indx is None and isinstance(self, imageregion):
                # if we make it here, check p2 (the last point) to self.points[indeces[0]] (the first point)
                line = shapely.geometry.LineString([p2.asTuple(), self.points[indeces[0]].asTuple()])
                if line.distance(cp.asShapely()) < clickRadius:
                    indx = self.getNextIndex()          # if it matches, insert at the end
        return indx
    
    def insertPoint(self, x, y, index):
        """Insert a point at index, shifting all higher-index points up."""
        self.shiftPointsUp(index)
        self.points[index] = imagepoint(x, y, index=index, color=self.color)
    
    def removePoint(self, index):
        """Remove the point at index and shift all points down to correspond with the deletion."""
        if index in self.points:
            self.points.pop(index)
        self.shiftPointsDown(index)
    
    def shiftPointsUp(self, index):
        # shift the points up
        for i in sorted(self.points.keys())[::-1]:
            if i >= index:
                p = self.points.pop(i)
                p.shiftUp()
                self.points[p.getIndex()] = p
            else:
                break
    
    def shiftPointsDown(self, index):
        # shift the points up
        for i in sorted(self.points.keys()):
            if i <= index:
                continue
            else:
                p = self.points.pop(i)
                p.shiftDown()
                self.points[p.getIndex()] = p
        
    def getObjectDict(self):
        # return a dictionary representing the object, including its name, index, color, type, and all of its points
        indx = str(self.getIndex())
        d = {'name': str(self.name)}
        d['index'] = indx
        d['color'] = str(self.color)
        d['type'] = self.__class__.__name__
        d['_points'] = {}
        for i, p in self.points.iteritems():
            d['_points'][str(i)] = p.asList()
        return {indx: d}
    
    def clickedOnPoint(self, cp, clickRadius):
        """Return whether the click cp was on a point of the region or not."""
        pt = None
        minDist = clickRadius
        for p in self.points.values():
            d = p.distance(cp)
            if d < minDist:
                minDist = d
                pt = p
        return pt
    
    def loadPointDict(self, pointDict):
        self.points = ObjectCollection()
        for i, p in pointDict.iteritems():
            x, y = map(int, p)
            indx = int(i)
            self.points[indx] = imagepoint(x, y, indx, color=self.color)
    
    def getFirstIndex(self):
        return min(self.points.keys()) if len(self.points) > 0 else 1
    
    def getLastIndex(self):
        return max(self.points.keys()) if len(self.points) > 0 else 1
    
    def getNextIndex(self):
        if len(self.points) == 0:
            return self.getFirstIndex()
        else:
            return self.getLastIndex() + 1
    
    def setColor(self, color):
        self.color = cvgui.getColorCode(color)
        if hasattr(self, 'points'):
            for p in self.points.values():
                p.setColor(color)
    
class imageline(MultiPointObject):
    """A class representing a line drawn on an image, i.e. a MultiPointObject with two ends."""
    def __init__(self, index=None, name='', color='random'):
        super(imageline, self).__init__(index=index, name=name, color=color)
        
    def linestring(self):
        if len(self.points) >= 2:
            return shapely.geometry.LineString(self.asTuple())
        
    def genShapelyObj(self):
        self.shapelyObj = self.linestring()
    
# TODO imagespline object based on imageline, but performs spline estimate with scipy and draws that
class imagespline(imageline):
    """A class representing a spline created (approximated) from a set of points."""
    def __init__(self, index=None, name='', color='random', degree=3):
        super(imageline, self).__init__(index=index, name=name, color=color)
        
        # spline-specific stuff
        self.degree = degree if degree <= 5 else 5          # limit to max 5 (according to scipy spline function)
        self.x = []
        self.y = []
        self.splineObj = None
        self.splinePointsX = None
        self.splinePointsY = None
        self.splinePointsList = None
        
    def computeSpline(self):
        """Estimate the spline with the points we have."""
        if len(self.points) > self.degree:
            # pull out the "data points"
            self.x = []
            self.y = []
            px = sorted([p.x for p in self.points.values()])
            for x in px:
                # get all the y's at this x (probably only 1, but maybe 2, theoretically any number (but unlikely)
                ys = self.points.listAttrs(self.points.listEqAttrKeys('x', x), 'y')
                for y in sorted(ys):
                    self.x.append(x)
                    self.y.append(y)
            
            # estimate the spline
            self.splineObj = scipy.interpolate.UnivariateSpline(self.x, self.y, k=self.degree)
    
    def pointsForDrawing(self):
        """Create a vector of points for plotting on the image, returning the clicked points if we don't have enough for a spline."""
        if len(self.points) > self.degree:
            self.computeSpline()
            if self.splineObj is not None:
                self.xMin = min(self.x)
                self.xMax = max(self.x)
                self.splinePointsX = np.linspace(self.xMin, self.xMax, (self.xMax-self.xMin)+1)
                self.splinePointsY = self.splineObj(self.splinePointsX)
                self.splinePointsList = zip(self.splinePointsX, self.splinePointsY)
                return self.splinePointsList
        return self.asTuple()       # return the points as a tuple if we con't do the spline
    
    def genShapelyObj(self):
        self.shapelyObj = shapely.geometry.LineString(self.pointsForDrawing())
        
    #def distance(self):
        #"""Calculate the distance to the closest point on the spline."""
        

class imageregion(MultiPointObject):
    """A class representing a region of an image, i.e. a closed MultiPointObject."""
    def __init__(self, index=None, name='', color='random'):
        super(imageregion, self).__init__(index=index, name=name, color=color)
        
        self.shapelyPolygon = None
        
    def boundary(self):
        if len(self.points) >= 3:
            return shapely.geometry.LinearRing(self.asTuple())
    
    def genShapelyObj(self):
        self.shapelyObj = self.boundary()
    
    def polygon(self):
        if len(self.points) >= 3:
            return shapely.geometry.Polygon(self.asTuple())
    
    def genShapelyPolygon(self):
        self.shapelyPolygon = self.polygon()
    
class ObjectCollection(dict):
    """A collection of objects that have a distance method that
       accepts a single argument and returns the distance between
       the object and itself. Used to easily select the closest
       thing to a """
    def getClosestObject(self, o):
        """Returns the key of the object that is closest to the object o."""
        minDist = np.inf
        minI = None
        for i, p in self.iteritems():
            d = p.distance(o)
            if d < minDist:
                minDist = d
                minI = i
        return minI
    
    def sortByDistance(self, obj, reverse=False):
        """Get the a list of all the objects in the collection sorted by
           their distance from object obj, starting with the closest (unless
           reverse is True."""
        # get the distance between all the objects and obj
        objDists = {i: obj.distance(o) for i, o in self.iteritems()}
        sortedDists = sorted(objDists.values())
        if reverse:
            sortedDists = sortedDists[::-1]
        sortedObjects = []
        for dist in sortedDists:
            # get the key for the object
            dkey = None
            for i, d in objDists.iteritems():
                if d == dist:
                    dkey = i
                    break
            if dkey in sortedDists:
                sortedDists.pop(dkey)                   # remove the object once we sort it
                sortedObjects.append(self[dkey])
        return sortedObjects
    
    def listEqAttrKeys(self, attrName, attrVal):
        l = []
        for k,o in self.iteritems():
            if hasattr(o, attrName) and getattr(o, attrName) == attrVal:
                l.append(k)
        return l
    
    def listAttrs(self, keys, attrName):
        l = []
        for k in keys:
            o = self[k]
            if hasattr(o, attrName):
                l.append(getattr(o, attrName))
        return l
    
    def getFirstIndex(self):
        intkeys = self.getIntKeys()
        return min(intkeys) if len(intkeys) > 0 else 1
    
    def getLastIndex(self):
        intkeys = self.getIntKeys()
        return max(intkeys) if len(intkeys) > 0 else 1
    
    def getIntKeys(self):
        return [k for k in self.keys() if isinstance(k, int)]
    
    def getNextIndex(self):
        if len(self) == 0:
            return self.getFirstIndex()
        else:
            return self.getLastIndex() + 1
    
    def append(self, o):
        """Add the object o to the next slot."""
        i = self.getNextIndex()
        self[i] = o
    