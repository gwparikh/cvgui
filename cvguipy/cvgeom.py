#!/usr/bin/python

"""Classes and functions for geometry operations."""

import os, sys, time, traceback
import random
from collections import OrderedDict

import numpy as np
import shapely.geometry
import scipy.interpolate

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
                    print("Problem loading color {} . Please check your inputs.".format(color))
        elif isinstance(color, tuple) and len(color) == 3:
            try:
                return tuple(map(int, color))           # in case we got a tuple of strings
            except ValueError or TypeError:
                print("Problem loading color {} . Please check your inputs.".format(color))
        else:
            return cvColorCodes[default]

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
                print("Object {} has no attribute '{}' !".format(self, k))
    
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
        self.color = getColorCode(color)
    
    def distance(self, o):
        """Calculate the distance between ourself and object o (relies on the genShapelyObj method)."""
        self.genShapelyObj()
        o.genShapelyObj()
        if self.shapelyObj is not None and o.shapelyObj is not None:
            return self.shapelyObj.distance(o.shapelyObj)            # gives distance from the point to the closest point on the boundary, whether it's inside or outside
    
    def asShapely(self):
        self.genShapelyObj()
        return self.shapelyObj
    
    def hasShapelyObj(self):
        """
        Return whether or not this object has a shapely object associated with
        it (note that it may or may not be updated if the object has changed).
        """
        return self.shapelyObj is not None
    
    def asTuple(self):
        print(self.__class__.__name__)
        raise NotImplementedError
    
    def genShapelyObj(self):
        print(self.__class__.__name__)
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
        return "<{} {} @ {} of [{}, {}]>".format(self.__class__.__name__, self.getIndex(), self.iNow, self.firstInstant, self.lastInstant) #, self.objects)
    
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
    
    def setiNow(self, i):
        """Set the value for iNow (the current point in time)."""
        self.iNow = i
        if not self.existsAtInstant(self.iNow):
            self.shapelyObj = None
    
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
    
    def distance(self, o):
        """Calculate the distance between ourself and object o (relies on the genShapelyObj method)."""
        self.genShapelyObj()
        o.genShapelyObj()
        if self.shapelyObj is not None and o.shapelyObj is not None:
            return self.shapelyObj.distance(o.shapelyObj)            # gives distance from the point to the closest point on the boundary, whether it's inside or outside
    
    def genShapelyObj(self):
        #self.shapelyObj = None
        if self.iNow is not None:
            if self.existsAtInstant(self.iNow):
                o = self.getObjectAtInstant(self.iNow)
                if o is not None:
                    o.genShapelyObj()
                    self.shapelyObj = o.shapelyObj
                    #print(self.shapelyObj)
            else:
                self.shapelyObj = None

class imagepoint(PlaneObject):
    """
    A class representing a point selected on an image.  Coordinates are stored
    as integers to correspond with pixel coordinates.
    """
    def __init__(self, x=None, y=None, **kwargs):
        super(imagepoint, self).__init__(**kwargs)
        
        self.x = int(round(x)) if x is not None else x
        self.y = int(round(y)) if y is not None else y
        
        # linear distance of this point along a line to which it belongs (if applicable)
        self.linearDistance = None
    
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
    
    def asColumnVector(self):
        return np.array([[self.x],
                         [self.y]])
    
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
        return [self.points[i].asTuple() for i in sorted(self.points.keys())]
    
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
        self.color = getColorCode(color)
        if hasattr(self, 'points'):
            for p in self.points.values():
                p.setColor(color)
    
    def setPointDistance(self, p):
        """
        Set the linearDistance on point p as the distance along the geometry
        from the first point to that point.
        """
        if not self.hasShapelyObj():
            self.genShapelyObj()
        if not p.hasShapelyObj():
            p.genShapelyObj()
        p.linearDistance = self.shapelyObj.project(p.shapelyObj)
    
    def setPointDistances(self):
        """
        Set the linearDistance on each point as the distance along the
        geometry from the first point to that point.
        """
        if not self.hasShapelyObj():
            self.genShapelyObj()
        for p in self.points.values():
            self.setPointDistance(p)
    
    def getSegmentIndex(self, d):
        """
        Return the index of the line segment that contains the point that is
        linear distance d from the beginning of the line. The index will be
        the index of the starting point, up to nPoints - 1. Must be called
        after the setPointDistances() method.
        """
        # iterate over points in order
        for i in sorted(self.points.keys()):
            if i == self.getLastIndex():
                # if the last point, return the second to last index
                return i - 1
            
            # get the next point in the line and check the distance
            lp = self.points[i+1]
            
            # if the next point in line is farther than d, we're done
            if lp.linearDistance is None:
                self.setPointDistance(lp)
            if lp.linearDistance >= d:
                return i
    
    def getLineSegment(self, segmentIndex):
        """
        Return the two endpoints of the line segment noted by segmentIndex
        (which should be the index of the first point). If segmentIndex is
        the last point index, the last available segment is returned.
        """
        if segmentIndex == self.getLastIndex():
            segmentIndex -= 1
        return self.points[segmentIndex], self.points[segmentIndex+1]
    
    def sortPointsByLineSegment(self, points):
        """
        Sort the list of points by the closest line segment of the MultiPoint
        object, where points is a list of shapely point objects (or point-like
        objects with an asShapely() method). A dict will be returned where the
        key is the line segment number (starting with 1, where 1 is the line
        segment between the 1st and 2nd points, 2 is the line segment between
        the 2nd and 3rd points, and so on) and each value is the list of
        points associated with that line segment.
        """
        # initialize the dict for sorted points
        sortedPoints = {}
        
        # make sure we have a shapely object for the line string
        self.genShapelyObj()
        
        # loop over all the points
        for p in points:
            # make sure we have a shapely point
            if not isinstance(p, shapely.geometry.point.Point):
                p = p.asShapely()
            
            # project the point to the line
            d = self.shapelyObj.project(p)
            
            # get the index of the starting point for that line segment
            i = self.getSegmentIndex(d)
            
            # add it to the dict
            if i not in sortedPoints:
                sortedPoints[i] = []
            sortedPoints[i].append(p)
        return sortedPoints
    
class imageline(MultiPointObject):
    """
    A class representing a line drawn on an image, i.e. a MultiPointObject with two ends
    that forms a continuous line.
    """
    @classmethod
    def rotationMatrixToNegY(cls, a, b):
        """
        Get the rotation matrix for the angle made between segment ab and the
        -Y-axis, assuming a +Y-down convention and returning a matrix for
        counter-clockwise rotation (unless clockwise is True). Note that this
        assumes a passive transformation is occurring, i.e. that only the
        coordinate system is changing. For an active transformation (i.e.
        actually rotating the points), the opposite action should be applied,
        e.g. by using the clockwise passive transformation rotation matrix 
        for a counter-clockwise active transformation.
        
        For details, see: https://en.wikipedia.org/wiki/Rotation_matrix
        particularly: https://en.wikipedia.org/wiki/Rotation_matrix#Ambiguities
        """
        # set a as the origin and get the x and y values of the ray
        x = b.x-a.x
        y = b.y-a.y
        
        # calculate the angle between the line and the +X-axis
        theta = np.arctan2(y,x)
        
        # get to -Y-axis (up)
        if theta < 0:
            # if theta is negative (above X-axis), take as 90 degrees minus
            # absolute value, which makes a CCW rotation for the 1st upper-
            # right quadrant and a CW rotation for the upper-left quadrant
            theta = np.pi/2. - abs(theta)
        else:
            # otherwise (theta positive or 0), add 90 degrees to get a CCW 
            # rotation angle to get to -Y-axis (up)
            theta += np.pi/2.
        
        # calculate sin and cos
        sin = np.sin(theta)
        cos = np.cos(theta)
        
        # return the rotation matrix (assuming +Y-down, passive transformation)
        # TODO/NOTE I thought the left-handed coordinate system plus the
        # passive transformation negated each other, but testing seems to prove
        # otherwise - keep testing to ensure this is true
        return np.array([[ cos, sin],
                         [-sin, cos]])
    
    @classmethod
    def sortPointsBySideSegment(cls, points, a, b):
        """
        Sort the list of (shapely) points by which side of the line segment
        represented by points a and b they are on. Points to the left of the
        line are considered to be on the left, and points on or to the right
        of the line are considered to be on the right. Returns a tuple in the
        form (leftPoints, rightPoints)
        """
        # turn the list of points into a matrix (where each point is a column vector)
        pointMat = np.hstack([p.xy for p in points])
        
        # transform the points so a is the origin
        aVec = a.asColumnVector()
        pointMat_A = pointMat - aVec
        
        # get the rotation matrix
        rot = cls.rotationMatrixToNegY(a, b)
        
        # multply the matrices to rotate the coordinate system
        pointMat_rot = np.matmul(rot, pointMat_A)
        
        # points with X < 0 are on the left, X >= 0 on the right
        pointMat_rotX = pointMat_rot[0]
        pointMat_rotY = pointMat_rot[1]
        leftInds = pointMat_rotX < 0
        rightInds = pointMat_rotX >= 0
        leftPoints = zip(pointMat_rotX[leftInds], pointMat_rotY[leftInds])
        rightPoints = zip(pointMat_rotX[rightInds], pointMat_rotY[rightInds])
        return leftPoints, rightPoints
    
    def linestring(self):
        if len(self.points) >= 2:
            return shapely.geometry.LineString(self.asTuple())
        
    def genShapelyObj(self):
        self.shapelyObj = self.linestring()
    
    def sortPointsBySide(self, points):
        """
        Sort the list of points according to which side of the line they fall.
        Points will be on either the left or right side of the line relative
        to the line segment to which they are closest. Left and right are
        defined as the -X and +X side, respectively, of the grid formed by
        setting the line segment in question as the Y-axis (i.e. X = 0).
        Returns a tuple in the form (leftPoints, rightPoints).
        """
        # first sort the points by line segment
        byLineSegment = self.sortPointsByLineSegment(points)
        
        # now go through by line segment and sort them by the side segment
        leftPoints, rightPoints = [], []
        for i in sorted(byLineSegment.keys()):
            points = byLineSegment[i]
            a = self.points[i]
            b = self.points[i+1]
            leftPointsSeg, rightPointsSeg = self.sortPointsBySideSegment(points, a, b)
            leftPoints.extend(leftPointsSeg)
            rightPoints.extend(rightPointsSeg)
        return leftPoints, rightPoints
    
    def getRatioPerSide(self, points):
        """Get the ratio of points that are on the left or right side of the line."""
        # sort points by side
        leftPoints, rightPoints = self.sortPointsBySide(points)
        
        # get ratios
        nPoints = float(len(points))
        percLeft = len(leftPoints)/nPoints
        percRight = len(rightPoints)/nPoints
        return percLeft, percRight
    
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

class LaneCollection(object):
    """
    A collection of lanes on a road. Lanes should be defined in a configuration
    file as lines (in the cvgui format) and named using the form:
    lane_{number}_{side}, where number is the number of the lane (where the
    lowest-numbered lane is the rightmost lane), and side is the side of the
    lane on which the line is drawn. In cases where the camera is on the
    starboard side of (some) vehicles, side should be 'R', while in cases
    where the camera is on the port side (some) of vehicles, side should be 
    'L' (note that this is not case-sensitive). This allows the algorithm to
    take the height of the vehicles into account when assigning the most
    likely lane. In cases where the camera is directly above the vehicles, the
    side chosen will have little effect on the results, as vehicles will not
    overlap noticeably.
    """
    # TODO we could potentially have this work with multiple biases or directions
    # of travel by adding a direction field or allowing a no-bias lane, but that
    # gets complicated and we don't need it now...
    
    def __init__(self, regions):
        # assume we are dealing with all geometric objects, so filter for lanes
        # lanes will be named in the form: lane_{number}_{side}
        self.lanes = OrderedDict()
        self.definedRight = None
        for objName, lane in sorted(regions.items()):
            objNameLower = objName.lower()
            if 'lane' in objNameLower:
                try:
                    jnk, laneNum, defSide = objNameLower.split('_')
                except ValueError:
                    raise Exception("Lanes must be named in the form 'lane_{number}_{side}' (case insensitive)! See help(cvgeom.LaneCollection) for more information.")
                
                # add some information to the lane
                lane.num = int(laneNum)
                lane.defSide = defSide
                
                # keep track of the direction we start on
                if self.definedRight is None:
                    if defSide == 'r':
                        self.definedRight = True
                    elif defSide == 'l':
                        self.definedRight = False
                else:
                    if defSide == 'r' and not self.definedRight or defSide == 'l' and self.definedRight:
                        raise Exception("Conflicting lane definitions. You must define lanes on EITHER the right side OR the left side of the lane. Using different sides is not currently supported!")
                
                # add the lane to the lane dict keyed on the number
                self.lanes[lane.num] = lane
        # get number of lanes
        self.nLanes = len(self.lanes)
        
    def assignLaneAtInstant(self, imgObject, i, minPercAbove=0.70):
        """
        Determine which lane the object is in at instant i. Lanes will be
        checked in order from right to left if they are defined on the right
        side of the lane, and from left to right if they are defined on the
        left side of the lane, to account for the height of vehicles. Vehicles
        must be at least minPercAbove above the boundary (so on the left if
        lanes are defined on the right, or on the right if lanes are defined
        on the left) to be allowed in the lane, otherwise it will be skipped
        (to prevent shadows from causing false detections).
        
        Returns the number of the lane (numbered starting at the right,
        regardless of which side lanes are defined on) if there is a match,
        and None otherwise.
        """
        if not imgObject.existsAtInstant(i):
            raise Exception("Object {} does not exist at instant {} !".format(imgObject.getNum(), i))
        
        # get the features of this object at instant i
        featPos = imgObject.getFeaturePositionsAtInstant(i)
        
        # go through the lanes - if we start at the right in decreasing order, otherwise the other way
        orderedLanes = reversed(self.lanes.items()) if self.definedRight else self.lanes.items()
        for laneNum, lane in orderedLanes:
            # get the percent of features on the left and right of lane
            percLeft, percRight = lane.getRatioPerSide(featPos)
            
            # above is to the left if defined on right and to the right if on left
            if self.definedRight:
                percAbove, percBelow = percLeft, percRight
            else:
                percAbove, percBelow = percRight, percLeft
            
            # if percAbove is more than minPercAbove, this is the lane
            if percAbove >= minPercAbove:
                return laneNum
    
    def assignLaneObject(self, imgObject, **kwargs):
        """
        Determine which lane the object is in at all points in its trajectory,
        writing the result to its lane attribute.
        """
        # reset the lane
        imgObject.obj.lane = []
        
        # go through each instant
        for i in imgObject.getTimeInterval():
            imgObject.obj.lane.append(self.assignLaneAtInstant(imgObject, i, **kwargs))
    
    def assignLane(self, imgObjects, **kwargs):
        """
        Determine which lane each of the given objects is in at all points in
        its trajectory, writing the result to the lane attribute of each
        trajectory.
        """
        for o in imgObjects:
            self.assignLaneObject(o, **kwargs)
    