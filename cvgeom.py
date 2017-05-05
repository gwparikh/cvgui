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

def deg2rad(deg):
    return np.pi*deg/180.0

def rad2deg(rad):
    return 180.0*rad/np.pi

# TODO - should we make this more like the other objects below?
def box(p1, p2):
    xMin = min(p1.x, p2.x)
    xMax = max(p1.x, p2.x)
    yMin = min(p1.y, p2.y)
    yMax = max(p1.y, p2.y)
    return shapely.geometry.box(xMin, yMin, xMax, yMax)

class IndexableObject(object):
    """An indexable-object that can be named and selected."""
    def __init__(self, index=None, name='', showIndex=True, selected=False, hidden=False, frameNumber=None):
        self.setIndex(index)
        self.name = name
        self.selected = selected
        self.hidden = hidden
        self.showIndex = showIndex
        self.frameNumber = frameNumber
    
    def replace(self, **kwargs):
        """Replace the attributes specified by keyword-argument."""
        for k, v in kwargs.iteritems():
            if hasattr(self, k):
                setattr(self, k, v)
            else:
                print "Object {} has no attribute '{}' !".format(self, k)
    
    def __repr__(self):
        return "<{}>".format(self.getObjStr)
    
    def getObjStr(self):
        s = "{} {}".format(self.__class__.__name__, self.getNameStr())
        return s
    
    def getNameStr(self):
        s = "{}".format(self.index)
        if self.name is not None and len(self.name) > 0 and self.index != self.name:
            s += " ({})".format(self.name)
        return s
    
    def getIndex(self):
        return self.index
    
    def setIndex(self, i):
        indx = i
        for t in [int, float]:
            try:                    # try to get a numerical value so we can sort on this index
                indx = t(i)
            except (TypeError, ValueError) as e:
                pass
        self.index = i          # default to same type if all else fails
    
    def isHidden(self):
        return self.hidden
    
    def hide(self):
        self.hidden = True
    
    def unhide(self):
        self.hidden = False
    
    def toggleHidden(self):
        # call the methods so they can be overridden
        if self.hidden:
            self.unhide()
        else:
            self.hide()
    
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
    def __init__(self, color='random', **kwargs):
        super(PlaneObject, self).__init__(**kwargs)
        self.setColor(color)
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
        print self.__class__.__name__
        raise NotImplementedError
    
    def genShapelyObj(self):
        print self.__class__.__name__
        raise NotImplementedError

class PlaneObjectTrajectory(PlaneObject):
    """
    A class for holding a trajectory of a moving PlaneObject over the time interval
    [firstInstant, lastInstant].
    """
    def __init__(self, firstInstant, lastInstant, objects, iNow=None, showObject=True, imageObject=None, **kwargs):
        """
        Construct the trajectory object.
        
        Arguments:
            firstInstant : Integer
            lastInstant  : Integer
            objects      : list of cvgeom.PlaneObject-subclass objects 
                           of length lastInstant-firstInstant+1
        """
        super(PlaneObjectTrajectory, self).__init__(**kwargs)
        
        self.firstInstant = firstInstant
        self.lastInstant = lastInstant
        self.objects = objects
        self.iNow = iNow
        self.hidden = not showObject
        
        # if we are constructed from an image object, we will keep a handle to that object so we can manipulate it from the GUI
        self.imageObject = imageObject
        
    def __repr__(self):
        return "<{} {} [{}, {}]: {}>".format(self.__class__.__name__, self.getIndex(), self.firstInstant, self.lastInstant, self.objects)
    
    @classmethod
    def fromImageObject(cls, imgObj):
        return cls(imgObj.obj.getFirstInstant(), imgObj.obj.getLastInstant(), imgObj.imgBoxes, imageObject=imgObj)
    
    def hide(self):
        """
        Hide the object by setting the hidden attribute, also setting it on the
        imageObject if we can.
        """
        super(PlaneObjectTrajectory, self).hide()
        if hasattr(self.imageObject,'hide'):
            self.imageObject.hide()
    
    def unhide(self):
        """
        Unhide the object by setting the hidden attribute, also setting it on the
        imageObject if we can.
        """
        super(PlaneObjectTrajectory, self).unhide()
        if hasattr(self.imageObject,'unhide'):
            self.imageObject.unhide()
    
    def select(self):
        self.selected = True
        for o in self.objects:
            o.select()
    
    def deselect(self):
        self.selected = False
        for o in self.objects:
            o.deselect()
    
    def existsAtInstant(self, i):
        exists = False
        if all([self.firstInstant,self.lastInstant]):
            exists = i >= self.firstInstant and i <= self.lastInstant
        return exists
    
    def getInstantIndex(self, i):
        if self.existsAtInstant(i):
            return i - self.firstInstant
    
    def getTimeInterval(self):
        tint = []
        if all([self.firstInstant,self.lastInstant]):
            tint = range(self.firstInstant, self.lastInstant+1)
        return tint
    
    def getObjectAtInstant(self, i):
        indx = self.getInstantIndex(i)
        if indx is not None:
            return self.objects[indx]
    
    # TODO is there a way to avoid duplicating the code here? perhaps with a metaclass?
    def asTuple(self):
        if self.iNow is not None:
            o = self.getObjectAtInstant(self.iNow)
            if o is not None:
                return o.asTuple()
    
    def genShapelyObj(self):
        #self.shapelyObj = None
        if self.iNow is not None:
            o = self.getObjectAtInstant(self.iNow)
            if o is not None:
                o.genShapelyObj()
                self.shapelyObj = o.shapelyObj
                #print self.shapelyObj

class imagepoint(PlaneObject):
    """A class representing a point selected on an image.  Coordinates are stored as
       integers to correspond with pixel coordinates."""
    def __init__(self, x=None, y=None, **kwargs):
        super(imagepoint, self).__init__(**kwargs)
        
        self.x = int(round(x)) if x is not None else x
        self.y = int(round(y)) if y is not None else y
    
    @classmethod
    def fromPoint(cls, p, **kwargs):
        return cls(x=p.x,y=p.y, **kwargs)
        
    def __repr__(self):
        return "<{}: ({}, {})>".format(self.getObjStr(), self.x, self.y)
        
    def __add__(self, p):
        return imagepoint(self.x+p.x, self.y+p.y)

    def __sub__(self, p):
        return imagepoint(self.x-p.x, self.y-p.y)
    
    def __neg__(self):
        return imagepoint(-self.x, -self.y)
    
    def __div__(self, s):
        return imagepoint(self.x/s, self.y/s)
    
    def __mul__(self, s):
        return imagepoint(self.x*s, self.y*s)
    
    def isNone(self):
        return self.x is None or self.y is None
        
    def asTuple(self):
        return (self.x, self.y)
    
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
    
class fimagepoint(imagepoint):
    """An imagepoint class that supports floating point coordinates
       (for when we need the precision and aren't drawing on an image)."""
    # override the constructor to take out the rounding and integer conversion
    def __init__(self, x=None, y=None, **kwargs):
        super(fimagepoint, self).__init__(**kwargs)
        self.x = float(x) if x is not None else x
        self.y = float(y) if y is not None else y
        
class MultiPointObject(PlaneObject):
    """A class representing a multi-point object, defined as an ordered
       collection of points."""
    def __init__(self, points=None, **kwargs):
        super(MultiPointObject, self).__init__(**kwargs)
        
        self.points = ObjectCollection() if points is None else points
        
        # set the color on any points we have
        for p in self.points.values():
            p.setColor(self.color)
    
    @classmethod
    def fromPointList(cls, points, **kwargs):
        """
        Create a MultiPointObject from a list of points, represented either
        as imagepoint's or as a 2-item list/tuple.
        """
        if isinstance(points, ObjectCollection):
            pts = points
        elif (isinstance(points, list) or isinstance(points, tuple)) or isinstance(points, np.ndarray):
            pts = ObjectCollection()
            for p in points:
                if isinstance(p, list) or isinstance(p, tuple) or isinstance(p, np.ndarray) and len(p) == 2:
                    pts.append(imagepoint(p[0],p[1]))
                elif isinstance(p, imagepoint):
                    pts.append(p)
                else:
                    raise TypeError('Points should be either a 2-item list/tuple or Nx2 numpy array, or imagepoint objects')
        else:
            raise TypeError('Points should be contained in either a list, tuple, numpy array, or ObjectCollection.')
        return cls(points=pts, **kwargs)
    
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
        return tuple(self.asList())
        
    def asList(self):
        #return [self.points[i].asTuple() for i in sorted(self.points.keys())]
        # TODO: this won't always work well, so may need to use sorted keys (see above)
        return [p.asTuple() for p in self.points.values()]
    
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
            self.points[indx] = imagepoint(x, y, index=indx, color=self.color)
    
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
    """
    A class representing a line drawn on an image, i.e. a MultiPointObject with two ends
    that forms a continuous line..
    """
    def linestring(self):
        if len(self.points) >= 2:
            return shapely.geometry.LineString(self.asTuple())
        
    def genShapelyObj(self):
        self.shapelyObj = self.linestring()
    
class dashedline(imageline):
    """
    A class representing a dashed line, i.e. a line consisting of alternating line segments.
    """
    pass

class imagespline(imageline):
    """A class representing a spline created (approximated) from a set of points."""
    def __init__(self, degree=3, **kwargs):
        super(imageline, self).__init__(**kwargs)
        
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
    
class imagebox(MultiPointObject):
    """A class representing a rectangular region in an image."""
    def __init__(self, pMin=None, pMax=None, **kwargs):
        super(imagebox, self).__init__(**kwargs)
        
        self.shapelyPolygon = None
        self.minX, self.minY, self.maxX, self.maxY = None, None, None, None
        if pMin is not None:
            self.minX, self.minY = pMin.x, pMin.y
        if pMax is not None:
            self.maxX, self.maxY = pMax.x, pMax.y
    
    def __repr__(self):
        return "<{} {}: [({},{}), ({},{})]>".format(self.__class__.__name__, self.index, self.minX, self.minY, self.maxX, self.maxY)
    
    def loadPointDict(self, pointDict):
        super(imagebox, self).loadPointDict(pointDict)
        self.refreshPoints()
        
    def genShapelyObj(self):
        if all([self.minX, self.minY, self.maxX, self.maxY]):
            self.shapelyObj = shapely.geometry.box(self.minX, self.minY, self.maxX, self.maxY)
    
    def polygon(self):
        if len(self.points) >= 3:
            return shapely.geometry.Polygon(self.asTuple())
    
    def refreshPoints(self):
        x, y = [], []
        for p in self.points.values():
            x.append(p.x)
            y.append(p.y)
        if len(x) > 0 and len(x) == len(y):
            self.minX = min(x)
            self.minY = min(y)
            self.maxX = max(x)
            self.maxY = max(y)
        for p in self.points.values():
            if p.selected:
                if p.x > self.minX and p.x < self.maxX:
                    self.maxX = p.x
                if p.y > self.minY and p.y < self.maxY:
                    self.minY = p.y
        #self.getImagePoints()
        
    def asList(self):
        return 
    
    def genShapelyPolygon(self):
        self.shapelyPolygon = self.polygon()
    
    def pointsForDrawing(self):
        pMin, pMax = None, None
        if all([self.minX, self.minY, self.maxX, self.maxY]):
            pMin = imagepoint(self.minX, self.minY)
            pMax = imagepoint(self.maxX, self.maxY)
        return pMin, pMax
    
    def getImagePoints(self):
        self.points = ObjectCollection()
        for x, y in [(self.minX, self.minY), (self.maxX, self.maxY)]:
            i = self.points.getNextIndex()
            self.points[i] = imagepoint(x, y, index=i, color=self.color)
        
    def finishBox(self):
        if len(self.points) >= 2:
            p1 = self.points[1]
            p2 = self.points[2]
            self.minX = min(p1.x, p2.x)
            self.minY = min(p1.y, p2.y)
            self.maxX = max(p1.x, p2.x)
            self.maxY = max(p1.y, p2.y)
            self.getImagePoints()

class imageregion(MultiPointObject):
    """A class representing a region of an image, i.e. a closed MultiPointObject."""
    def __init__(self, **kwargs):
        super(imageregion, self).__init__(**kwargs)
        
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
    """A collection of IndexableObject's"""
    def selectedObjects(self):
        """Return an ObjectCollection containing only the objects that are selected."""
        return ObjectCollection({i: o for i, o in self.iteritems() if o.selected})
    
    def getClosestObject(self, o):
        """Returns the key of the object that is closest to the object o."""
        minDist = np.inf
        minI = None
        for i, p in self.iteritems():
            d = p.distance(o)
            if d is not None and d < minDist:
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
    
    def append(self, o, setIndex=True):
        """Add the object o to the next slot."""
        i = self.getNextIndex()
        if setIndex:
            o.setIndex(i)
        self[i] = o
