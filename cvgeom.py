#!/usr/bin/python

"""Classes and methods for geometry operations."""

import os, sys, time, traceback
import numpy as np
import shapely.geometry
import cvgui

def cart2pol(x, y):
    rho = np.sqrt(x**2 + y**2)
    phi = np.arctan2(y, x)
    return(rho, phi)

def pol2cart(rho, phi):
    x = rho * np.cos(phi)
    y = rho * np.sin(phi)
    return(x, y)

# TODO make cvgeom module and move these there
class IndexableObject(object):
    """An indexable-object that can be named and selected."""
    def __init__(self, index=None, name=''):
        self.index = index
        self.name = name
        self.selected = False
    
    def __repr__(self):
        return "<{}>".format(self.getObjStr)
    
    def getObjStr(self):
        s = "{} {}".format(self.__class__.__name__, self.index)
        if len(self.name) > 0:
            s += " ({})".format(self.name)
        return s
    
    def getIndex(self):
        return self.index
    
    def setIndex(self, i):
        self.index = i
    
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
    
    def move(self, dp):
        """Move the object by moving all points in the object."""
        for p in self.points.values():
            p.move(dp)
    
    def asTuple(self):
        pList = []
        for p in self.points.values():
            pList.append(p.asTuple())
        return tuple(pList)
        
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
    
    